"""ESA WorldCover land-cover context features (Track A). CONTEXT ONLY - never a label.

Product: ESA WorldCover 10 m v200 (2021), 3x3-degree GeoTIFF tiles named by their lower-left corner, e.g. N21E072.
Tiles are fetched once into a local cache directory (see `tile_url`); reading is windowed via tifffile tile/strip
decoding, so a 36000x36000 tile is never loaded whole. Georeferencing is read from the GeoTIFF tags
(ModelPixelScale + ModelTiepoint) of each file, not assumed.

Missing data stays missing: a point whose tile is not cached -> status MISSING_NOT_FETCHED, all features NULL.
Pixels with value 0 (no data) are excluded and reported via `wc_nodata_frac`; they never count as any class.
Year mismatch: WorldCover 2021 vs FIRMS 2026 - recorded in provenance (`wc_product`), a known limitation.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import numpy as np

PRODUCT = "ESA_WorldCover_10m_2021_v200"
URL_TEMPLATE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
CLASSES = {10: "tree_cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built_up", 60: "bare_sparse",
           70: "snow_ice", 80: "water", 90: "herbaceous_wetland", 95: "mangroves", 100: "moss_lichen"}
NODATA = 0
RADIUS_M = 500
STATUS_OK, STATUS_MISSING, STATUS_PARTIAL, STATUS_READ_ERROR = "OK", "MISSING_NOT_FETCHED", "PARTIAL_TILE_MISSING", "READ_ERROR"


def tile_name(lat: float, lon: float) -> str:
    la, lo = math.floor(lat / 3) * 3, math.floor(lon / 3) * 3
    return f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"


def tile_url(tile: str) -> str:
    return URL_TEMPLATE.format(tile=tile)


def tile_path(cache_dir, tile: str) -> Path:
    return Path(cache_dir) / f"{PRODUCT}_{tile}_Map.tif"


class _Raster:
    """Windowed reader for a single-band tiled or stripped GeoTIFF."""

    def __init__(self, path):
        import tifffile
        self.tif = tifffile.TiffFile(path)
        p = self.page = self.tif.pages[0]
        sx, sy = p.tags["ModelPixelScaleTag"].value[:2]
        tp = p.tags["ModelTiepointTag"].value
        self.res_x, self.res_y = float(sx), float(sy)
        self.lon0 = float(tp[3]) - float(tp[0]) * self.res_x      # lon of pixel-corner (0,0)
        self.lat0 = float(tp[4]) + float(tp[1]) * self.res_y      # lat of pixel-corner (0,0)
        self.h, self.w = p.imagelength, p.imagewidth
        if p.is_tiled:
            self.bw, self.bh = p.tilewidth, p.tilelength
        else:
            self.bw, self.bh = self.w, p.rowsperstrip
        self.nbx = math.ceil(self.w / self.bw)
        self._blocks = {}

    def close(self): self.tif.close()

    def _block(self, by, bx):
        key = (by, bx)
        if key not in self._blocks:
            idx = by * self.nbx + bx
            off, n = self.page.dataoffsets[idx], self.page.databytecounts[idx]
            fh = self.tif.filehandle; fh.seek(off); raw = fh.read(n)
            data = self.page.decode(raw, idx)[0]
            self._blocks[key] = np.asarray(data).reshape(data.shape[-3], data.shape[-2])
        return self._blocks[key]

    def value(self, row, col):
        b = self._block(row // self.bh, col // self.bw)
        return int(b[row % self.bh, col % self.bw])

    def rowcol(self, lat, lon):
        return int(math.floor((self.lat0 - lat) / self.res_y)), int(math.floor((lon - self.lon0) / self.res_x))

    def contains(self, lat, lon):
        r, c = self.rowcol(lat, lon)
        return 0 <= r < self.h and 0 <= c < self.w

    def pixels_within(self, lat, lon, radius_m):
        """Yield values of pixels whose centres lie within radius_m of (lat, lon) and inside this raster."""
        dlat = radius_m / 111_320.0
        dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
        r0, c0 = self.rowcol(lat + dlat, lon - dlon)
        r1, c1 = self.rowcol(lat - dlat, lon + dlon)
        r0, c0, r1, c1 = max(r0, 0), max(c0, 0), min(r1, self.h - 1), min(c1, self.w - 1)
        coslat = math.cos(math.radians(lat))
        for r in range(r0, r1 + 1):
            plat = self.lat0 - (r + 0.5) * self.res_y
            for c in range(c0, c1 + 1):
                plon = self.lon0 + (c + 0.5) * self.res_x
                dy = (plat - lat) * 111_320.0; dx = (plon - lon) * 111_320.0 * coslat
                if dx * dx + dy * dy <= radius_m * radius_m:
                    yield self.value(r, c)


def _empty(tiles):
    f = {"wc_status": STATUS_MISSING, "wc_product": PRODUCT, "wc_tiles": ";".join(tiles), "wc_class_at_point": None,
         "wc_class_name_at_point": None, "wc_dominant_class_name_500m": None, "wc_n_pixels_500m": None,
         "wc_nodata_frac_500m": None}
    for name in CLASSES.values(): f[f"wc_frac_{name}_500m"] = None
    return f


def point_features(lat: float, lon: float, cache_dir, radius_m: float = RADIUS_M) -> dict:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    tiles = sorted({tile_name(a, b) for a in (lat - dlat, lat + dlat) for b in (lon - dlon, lon + dlon)})
    out = _empty(tiles)
    present = [t for t in tiles if tile_path(cache_dir, t).exists()]
    if tile_name(lat, lon) not in present:
        return out
    try:
        return _read_features(lat, lon, cache_dir, radius_m, tiles, present, out)
    except Exception as ex:  # noqa: BLE001 - e.g. codec needs `imagecodecs`; surfaced as UNKNOWN, never as a class
        f = _empty(tiles); f["wc_status"] = f"{STATUS_READ_ERROR}: {type(ex).__name__}: {str(ex)[:120]}"
        return f


def _read_features(lat, lon, cache_dir, radius_m, tiles, present, out):
    counts, n_all = Counter(), 0
    for t in present:
        ras = _Raster(tile_path(cache_dir, t))
        try:
            if ras.contains(lat, lon):
                v = ras.value(*ras.rowcol(lat, lon))
                out["wc_class_at_point"] = v if v != NODATA else None
                out["wc_class_name_at_point"] = CLASSES.get(v) if v != NODATA else None
            for v in ras.pixels_within(lat, lon, radius_m):
                counts[v] += 1; n_all += 1
        finally:
            ras.close()
    valid = n_all - counts.get(NODATA, 0)
    out["wc_status"] = STATUS_OK if len(present) == len(tiles) else STATUS_PARTIAL
    out["wc_n_pixels_500m"] = n_all
    out["wc_nodata_frac_500m"] = round(counts.get(NODATA, 0) / n_all, 4) if n_all else None
    for code, name in CLASSES.items():
        out[f"wc_frac_{name}_500m"] = round(counts.get(code, 0) / valid, 4) if valid else None
    if valid:
        code = max((c for c in counts if c != NODATA), key=lambda c: (counts[c], -c))
        out["wc_dominant_class_name_500m"] = CLASSES.get(code, f"unknown_{code}")
    return out
