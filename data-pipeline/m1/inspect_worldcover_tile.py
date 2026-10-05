"""Report the REAL properties of downloaded WorldCover tiles: compression, tiling, georeferencing, and whether this
environment can decode them (with or without `imagecodecs`). Use the result to decide dependencies; do not assume.

  python3 m1/inspect_worldcover_tile.py context_cache/worldcover/*.tif
"""
import json, sys
from pathlib import Path
import tifffile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thermwatch_core import context_worldcover as wc   # noqa: E402

def inspect(p):
    out = {"file": Path(p).name}
    try:
        with tifffile.TiffFile(p) as t:
            pg = t.pages[0]
            out.update(compression=str(pg.compression), tiled=pg.is_tiled, tile=(pg.tilelength, pg.tilewidth) if pg.is_tiled else None,
                       shape=list(pg.shape), dtype=str(pg.dtype), n_pages_overviews=len(t.pages),
                       pixel_scale=list(pg.tags["ModelPixelScaleTag"].value[:2]), tiepoint=list(pg.tags["ModelTiepointTag"].value[3:5]))
        r = wc._Raster(p)
        try: out["decode_test_value"] = r.value(r.h // 2, r.w // 2); out["decodable_here"] = True
        finally: r.close()
    except Exception as ex:  # noqa: BLE001
        out["decodable_here"] = False; out["error"] = f"{type(ex).__name__}: {ex}"
    try:
        import imagecodecs; out["imagecodecs_installed"] = imagecodecs.__version__
    except ImportError:
        out["imagecodecs_installed"] = None
    return out

if __name__ == "__main__":
    res = [inspect(p) for p in sys.argv[1:]]
    print(json.dumps(res, indent=1))
    sys.exit(0 if res and all(r.get("decodable_here") for r in res) else 1)
