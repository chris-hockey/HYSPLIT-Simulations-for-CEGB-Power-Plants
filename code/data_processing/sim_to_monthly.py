from pathlib import Path
import sys
import xarray as xr

ROOT = Path(__file__).resolve().parents[2]  # noqa: E402
sys.path.insert(0, str(ROOT / "code" / "simulation"))  # noqa: E402

from hysplit import PlantYear, HYSPLITRun  # noqa: E402
from hysplit.monthly_kernel import build_monthly_kernel  # noqa: E402
from hysplit.paths import RUNS_DIR  # noqa: E402


for run_dir in sorted(RUNS_DIR.iterdir()):
    if not run_dir.is_dir():
        continue  # not a run folder, ignore
    cdump = run_dir / f"cdump_{run_dir.name}.nc"
    if not cdump.exists():
        raise FileNotFoundError(f"missing daily cdump in run folder: {cdump}")
    plant_id, year_maj = run_dir.name.rsplit("_", 1)
    py = PlantYear.from_panel(plant_id, int(year_maj))
    build_monthly_kernel(py, overwrite=True)
