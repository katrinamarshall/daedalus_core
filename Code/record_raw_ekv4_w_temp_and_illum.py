import argparse
import dataclasses
import datetime
import pathlib
import json
import time

import neuromorphic_drivers as nd

dirname = pathlib.Path(__file__).resolve().parent

configuration = nd.prophesee_evk4.Configuration(
    biases=nd.prophesee_evk4.Biases(
        diff_off=102,  # default: 102
        diff_on=73,  # default: 73
    )
)

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("serial", help="Camera serial number (for example 00050423)")
parser.add_argument(
    "--recordings",
    default=str(dirname / "recordings"),
    help="Path of the directory where recordings are stored",
)
parser.add_argument(
    "--measurement-interval",
    default=0.1,
    type=float,
    help="Interval between temperature and illuminance measurements in seconds",
)
parser.add_argument(
    "--flush-interval",
    default=0.5,
    type=float,
    help="Maximum interval between file flushes in seconds",
)
args = parser.parse_args()

output_directory = pathlib.Path(args.recordings).resolve() / f"evk4_{args.serial}"
output_directory.mkdir(parents=True, exist_ok=True)
flush_interval = int(round(args.flush_interval * 1e9))
measurement_interval = int(round(args.measurement_interval * 1e9))
name = (
    datetime.datetime.now(tz=datetime.timezone.utc)
    .isoformat()
    .replace("+00:00", "Z")
    .replace(":", "-")
)

with nd.open(configuration=configuration, raw=True, serial=args.serial) as device:
    print(f"Successfully started EVK4 {args.serial}")

    # save the camera biases
    with open(output_directory / f"{name}_metadata.json", "w") as json_file:
        configuration_dict = dataclasses.asdict(configuration)
        configuration_dict["clock"] = configuration_dict["clock"].name
        json.dump(
            {
                "system_time": time.time(),
                "properties": dataclasses.asdict(device.properties()),
                "configuration": configuration_dict,
            },
            json_file,
            indent=4,
        )

    # save the events, samples (timings), and measurements (illuminance and temperature)
    events_cursor = 0
    with open(
        output_directory / f"{name}_events.raw",
        "wb",
    ) as events, open(
        output_directory / f"{name}_samples.jsonl",
        "wb",
    ) as samples, open(
        output_directory / f"{name}_measurements.jsonl",
        "wb",
    ) as measurements:
        start_time = time.monotonic_ns()
        next_flush = start_time + flush_interval
        next_measurement = start_time
        for status, packet in device:
            events.write(packet)
            events_cursor += len(packet)
            try:
                status_dict = dataclasses.asdict(status)
                status_dict["events_cursor"] = events_cursor
                samples.write(f"{json.dumps(status_dict)}\n".encode())
            except:
                pass
            if time.monotonic_ns() >= next_measurement:
                try:
                    measurement_dict = {
                        "system_time": time.time(),
                        "temperature": device.temperature_celsius(),
                        "illuminance": device.illuminance(),
                    }
                    measurements.write(f"{json.dumps(measurement_dict)}\n".encode())
                except:
                    pass
                next_measurement = time.monotonic_ns() + measurement_interval
            if time.monotonic_ns() >= next_flush:
                events.flush()
                samples.flush()
                measurements.flush()
                next_flush = time.monotonic_ns() + flush_interval
