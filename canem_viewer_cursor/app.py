import argparse
import tkinter as tk

from src.model.vehicle_model import VehicleModel
from src.services.pipeline import TelemetryPipeline
from src.ui.main_window import MainWindow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Formula Student EV telemetry viewer")
    parser.add_argument("--dbc", default="dbc/EM06CAN.dbc")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--bitrate", type=int, default=250000)
    parser.add_argument("--app-name", default="CANalyzer")
    parser.add_argument("--no-vector", action="store_true", help="Run without Vector hardware (show all DBC signals in gray)")
    return parser.parse_args()


def main() -> None:
    print("=" * 60)
    print("CANEM Viewer Starting...")
    print("=" * 60)
    
    args = parse_args()
    print(f"DEBUG: DBC path: {args.dbc}")
    print(f"DEBUG: No vector mode: {args.no_vector}")
    
    model = VehicleModel(dbc_path=args.dbc)
    print(f"DEBUG: VehicleModel created with {len(model.vehicle.pcbs)} PCBs")
    print(f"DEBUG: PCBs: {list(model.vehicle.pcbs.keys())}")
    
    pipeline = TelemetryPipeline(
        model=model,
        dbc_path=args.dbc,
        vector_channel=args.channel,
        vector_bitrate=args.bitrate,
        vector_app_name=args.app_name,
        no_vector=args.no_vector,
    )
    print("DEBUG: TelemetryPipeline created")
    
    root = MainWindow(model=model, pipeline=pipeline)
    print("DEBUG: MainWindow created")
    
    print("DEBUG: Starting pipeline...")
    pipeline.start()
    
    print("DEBUG: Starting main window...")
    root.protocol("WM_DELETE_WINDOW", lambda: on_close(root, pipeline))
    root.mainloop()


def on_close(root: tk.Tk, pipeline: TelemetryPipeline) -> None:
    pipeline.stop()
    root.destroy()


if __name__ == "__main__":
    main()
