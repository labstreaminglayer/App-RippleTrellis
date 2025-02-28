import typer

from lsl_ripple.device import RippleDevice
from lsl_ripple.stream import RippleStream


def main(targ_stream_type: str = "hi-res"):
    device = RippleDevice(targ_stream_type=targ_stream_type)
    stream = RippleStream(device)
    try:
        stream.start()
    except KeyboardInterrupt:
        print("Application interrupted. Exiting.")
        stream.shutdown()


if __name__ == "__main__":
    typer.run(main)
