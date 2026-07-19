import argparse
import tkinter as tk

from src.model.vehicle_model import VehicleModel
from src.services.pipeline import TelemetryPipeline
from src.ui.main_window import MainWindow
from src.can_layer.vector_interface import auto_detect_interface


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Formula Student EV telemetry viewer")
    parser.add_argument("--dbc", default="dbc/EM06CAN.dbc")
    parser.add_argument("--auto-detect", action="store_true", 
                        help="Detectar automàticament la interfície CAN disponible")
    parser.add_argument("--interface", choices=["vector", "pcan"], default="vector", 
                        help="CAN interface to use: vector or pcan")
    parser.add_argument("--channel", type=int, default=0, 
                        help="Vector channel (if using Vector interface)")
    parser.add_argument("--bitrate", type=int, default=250000,
                        help="CAN bitrate in bps")
    parser.add_argument("--app-name", default="CANalyzer",
                        help="Vector app name (if using Vector interface)")
    parser.add_argument("--pcan-channel", default="PCAN_USBBUS1",
                        help="PCAN channel (if using PCAN interface)")
    parser.add_argument("--no-vector", action="store_true", help="Run without Vector hardware (show all DBC signals in gray)")
    parser.add_argument("--debug", action="store_true", help="Enable debug output (log received CAN messages)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    # Detecció automàtica si s'especifica
    interface = args.interface
    pcan_channel = args.pcan_channel
    no_vector = args.no_vector
    
    if args.auto_detect:
        interface, config = auto_detect_interface(
            vector_channel=args.channel,
            vector_app_name=args.app_name,
            pcan_channel=args.pcan_channel,
        )
        if interface == "none":
            no_vector = True
        else:
            pcan_channel = config.get("pcan_channel", args.pcan_channel)
    
    model = VehicleModel(dbc_path=args.dbc)
    
    pipeline = TelemetryPipeline(
        model=model,
        dbc_path=args.dbc,
        vector_channel=args.channel,
        vector_bitrate=args.bitrate,
        vector_app_name=args.app_name,
        pcan_channel=pcan_channel,
        pcan_bitrate=args.bitrate,
        interface=interface,
        no_vector=no_vector,
        debug=args.debug,
    )
    
    root = MainWindow(model=model, pipeline=pipeline)
    
    pipeline.start()
    
    root.protocol("WM_DELETE_WINDOW", lambda: on_close(root, pipeline))
    root.mainloop()


def on_close(root: tk.Tk, pipeline: TelemetryPipeline) -> None:
    pipeline.stop()
    root.destroy()


if __name__ == "__main__":
    main()
