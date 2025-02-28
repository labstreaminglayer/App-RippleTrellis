import time
import typing

import numpy as np
import numpy.typing as npt
import xipppy as xp


CLOCK_RATE = 30_000
STREAM_RATES: dict = {
    "raw": CLOCK_RATE,
    "hi-res": 2_000,
    "lfp": 1_000
}


class RippleDevice:
    def __init__(
            self,
            targ_stream_type: str = "hi-res",  # for now only supporting raw, hi-res, lfp
            fetch_delay: float = 0.004,
    ):
        if targ_stream_type not in STREAM_RATES:
             raise Exception(f"Stream types other than {STREAM_RATES.keys()} are not supported")
        
        self._targ_st = targ_stream_type
        self._fetch_delay = fetch_delay
        try:
            udp_mode = xp._open()
            print("Connected through UDP")
        except:
            print("Failed to connect through UDP \nAttempting TCP")
            try:
                tcp_mode = xp._open(use_tcp=True)
                print("Connected through TCP")
            except:
                raise Exception("Could not connect to processor. \nMake sure power LED is connected and try again")

        # For each electrode, enable only the target stream, disable all others
        electrode_ids = xp.list_elec("all")
        self._elec_ids: list[int] = []
        for el_id in electrode_ids:
            for st in xp.get_fe_streams(int(el_id)):
                b_targ_st = st == self._targ_st
                xp.signal_set(el_id, st, b_targ_st)
                if b_targ_st:
                    self._elec_ids.append(int(el_id))

        # TODO: Filtering?

        self._t0 = xp.time()

    @property
    def stream_type(self):
        return self._targ_st

    @property
    def elec_ids(self) -> list[int]:
        return self._elec_ids

    @property
    def srate(self) -> float:
        return float(STREAM_RATES.get(self.stream_type, 1_000))

    def __del__(self):
        for st in ["raw", "stim", "hi-res", "lfp", "spk"]:
            for el_id in self._elec_ids:
                xp.signal_set(el_id, st, False)
        time.sleep(1.0)
        xp._close()

    @staticmethod
    def time() -> int:
        return xp.time()

    def fetch(self) -> typing.Tuple[npt.NDArray[np.float32], int]:
        t_now = xp.time()
        t_elapsed = max(0, (t_now - self._t0) / CLOCK_RATE)
        # Only fetch up to t_now - _fetch_delay, never beyond!
        fetch_points = max(int((t_elapsed - self._fetch_delay) * self.srate), 0)

        # Fetch
        data, timestamp = None, 0
        if fetch_points > 0:
            if self._targ_st == "raw":
                data, timestamp = xp.cont_raw(fetch_points, self._elec_ids, start_timestamp=self._t0)
            elif self._targ_st == "hi-res":
                data, timestamp = xp.cont_hires(fetch_points, self._elec_ids, start_timestamp=self._t0)
            elif self._targ_st == "lfp":
                data, timestamp = xp.cont_lfp(fetch_points, self._elec_ids, start_timestamp=self._t0)
            else:
                raise Exception(f"Unsupported ripple stream type: {self._targ_st} ")

        if data is not None:
            if not len(self._elec_ids):
                raise Exception("Data channel count iz zero. Are electrodes connected?")
            # Note atypical memory layout: channels x samples.
            data = np.array(data).reshape(len(self._elec_ids), -1)
            data = np.ascontiguousarray(data.T)
            if data.shape[0] > 0:
                if data.shape[0] != fetch_points:
                    raise Exception("API returned unexpected number of points. Data missing.")
                self._t0 += int(fetch_points * CLOCK_RATE / self.srate)
                timestamp = self._t0

        return data, timestamp
