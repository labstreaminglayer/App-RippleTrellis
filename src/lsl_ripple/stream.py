import time
import threading
import math
from sys import exit

import pylsl

from .device import RippleDevice, CLOCK_RATE


class RippleStream:
    def __init__(
        self,
        device: RippleDevice,
        chunk_dur: float = 0.010,
    ):
        if chunk_dur < 0.002:
            raise ValueError("Chunk duration must be at least 0.002s")
        self._device = device
        self._timeout_acquisition_sec = 10.0

        info = pylsl.StreamInfo(
            f"Ripple_{self._device.stream_type}",
            "EPhys",
            len(self._device.elec_ids),
            self._device.srate,
            "float32",
            f"RippleXippy{self._device.stream_type}",
        )
        info.desc().append_child_value("manufacturer", "Ripple")
        chns = info.desc().append_child("channels")
        for label in self._device.elec_ids:
            ch = chns.append_child("channel")
            ch.append_child_value("label", str(label))
        self._outlet = pylsl.StreamOutlet(info, chunk_size=0, max_buffered=360)
        self._expected_chunk_size = int(math.ceil(chunk_dur * self._device.srate))

        self._time_offset = 0.0
        self._time_gain = 1 / CLOCK_RATE
        self._thread = threading.Thread(target=self._time_sync_thread)
        self._thread.daemon = True  # Make the thread a daemon thread
        self._thread.start()

    def _rpl2lsl(self, ripple_time: int) -> float:
        return ripple_time * self._time_gain + self._time_offset

    def _time_sync_thread(self):
        while True:
            lsl_now = pylsl.local_clock()
            rpl_now = self._device.time()
            alpha = 0.05
            new_offset = lsl_now - rpl_now * self._time_gain
            self._time_offset = alpha * new_offset + (1 - alpha) * self._time_offset
            time.sleep(5.0)

    def shutdown(self):
        del self._outlet
        # del self._device

    def do_samples_bookeeping(self, num_samples) -> bool:
        continue_running: bool = True
        self.samples_pushed += num_samples
        if self.samples_pushed - self.samples_previous > self._device.srate:
            print(f"\tSamples steamed: {self.samples_pushed:12,}", end="\r")
            self.samples_previous = self.samples_pushed
            self.time_since_last_data = time.time()
        if time.time() - self.time_since_last_data > self._timeout_acquisition_sec:
            continue_running = False
        return continue_running

    def start(self):
        self.samples_pushed = 0
        self.samples_previous = self.samples_pushed
        self.time_since_last_data = time.time()
        # print("Stream stats:", end='\r')
        print(f"\tSamples streamed: \t\t\t\t", end="\r")
        while True:
            n_missing = self._expected_chunk_size
            data, ts = self._device.fetch()
            if data is not None and data.size > 0:
                self._outlet.push_chunk(data, self._rpl2lsl(ts))
                n_missing = self._expected_chunk_size - data.shape[0]
            samples_received = data.shape[0] if data is not None else 0
            if not self.do_samples_bookeeping(num_samples=samples_received):
                exit(
                    f"No data for more than {self._timeout_acquisition_sec}s. Aborting"
                )

            if n_missing > 0:
                sleep_time = n_missing / self._device.srate
                # print(f"Sleeping {sleep_time}")
                time.sleep(sleep_time)
