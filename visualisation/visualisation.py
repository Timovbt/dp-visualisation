import numpy as np
import time
import toml
import pylsl
import mne_lsl
from fire import Fire
from pathlib import Path
from dareplane_utils.stream_watcher.lsl_stream_watcher import StreamWatcher
from dareplane_utils.general.time import sleep_s
from dareplane_utils.signal_processing.filtering import FilterBank
from mne_lsl.stream import EpochsStream, StreamLSL,BaseStream
from mne import EvokedArray,combine_evoked
from pylsl import StreamInlet,StreamInfo,StreamOutlet
from visualisation.utils.logging import logger
from numpy.typing import NDArray
from scipy.signal import resample
X = None

class Visualisation():
    """
    Object to decode LSL-stream and send analysed data to Live_plot

    Parameters
    ----------
    marker_stream_name: str
        Name of the LSL stream where the stimulation logs to
    data_stream_name: str
        Name of incoming LSL stream with EEG-data
    decoder_stream_name: str
        Name of outgoing LSL stream to visualize processed data
    buffer_size_s: float   
    padding_size_s: float,
    max_eval_time_s: int
        Maximum time to spend on processing data in buffer
    t_sleep_s: float = 0.1

    selected_channels: list[str]
        Selected EEG-channels for data visualisation
    USED? output_port: int (default 8088)
        Port for live_plot server
    USED? output_address:str (default 127.0.0.1)
        Address for live_plot server
    band: list[int] (default [6,40])
        Limits for bandpass filter applied to incoming EEG-data

    Attributes
    ----------
    """

    def __init__(
            self,
            marker_stream_name: str,
            data_stream_name: str,
            decoder_stream_name: str,
            buffer_size_s: float,
            padding_size_s: float,
            start_eval_marker: str,
            max_eval_time_s: int,
            t_sleep_s: float = 0.1,
            selected_channels: list[str] | None = None,
            output_port: int=8088,
            output_address:str="127.0.0.1",
            band: list[int] = [6,40]
            ):
        
        self.marker_stream_name = marker_stream_name
        self.data_stream_name = data_stream_name
        self.buffer_size_s = buffer_size_s
        self.padding_size_s = padding_size_s
        self.start_eval_marker = start_eval_marker
        self.t_sleep_s = t_sleep_s
        self.selected_channels = selected_channels
        self.max_eval_time_s = max_eval_time_s
        self.output_port = output_port
        self.output_address = output_address
        self.band = band

        self.selected_ch_idx = None
        self.is_decoding: bool = False
        self.start_eval_time: float = 0.0
        self.internal_decoding_start_time: float = time.time()
        self.logger = logger

        self.input_mrk_sw: StreamWatcher | None = None
        self.input_sw: StreamWatcher | None = None
        self.epochstream = EpochsStream | None
        self.input_sfreq: int | None = None
        self.input_chs_info: list[dict[str, str]] | None = None
        self.filterbank: FilterBank | None = None
        self.output_sw: StreamWatcher | None = None
        self.classifier_input_sfreq = None

        info = StreamInfo(
                    name='output_average_stream',
                    type="data",
                    channel_count=350,
                    nominal_srate=2,
                    channel_format=pylsl.cf_float32,
                    source_id="output_average_stream",
                )
        self.outlet = StreamOutlet(info)

    def init_all(self) -> int:
        """Returns an int as this is exposed as a PCOMM `CONNECT_DECODER`"""

        logger.info("initializing decoder")
        self.connect_marker_stream()
        self.connect_data_stream()
        self.connect_epoch_stream()
        # self.create_filterbank()
        self.run()

        return 0

    def connect_epoch_stream(self):
         if self.input_mrk_stream != None and self.input_stream != None:
            self.epochstream = EpochsStream(
                            stream = self.input_stream,
                            bufsize = 10,
                            event_id= 1,
                            tmin=-0.2,
                            tmax=0.5,
                            event_channels=['0'],
                            event_stream = self.input_mrk_stream,
                            picks = self.selected_channels
                            ).connect(acquisition_delay=0.1)
            return 0
         else:
             logger.info("data stream and marker stream must be connected first") #TODO
             return 1

    def connect_marker_stream(self):
        self.input_mrk_stream = StreamLSL(self.buffer_size_s,stype="Markers",name=self.marker_stream_name)
        self.input_mrk_stream.connect(acquisition_delay=0.1,processing_flags="all")
        print(self.input_mrk_stream.ch_names)

    def connect_data_stream(self):
        self.input_stream = StreamLSL(self.buffer_size_s,stype="EEG",name=self.data_stream_name)
        self.input_stream.connect(acquisition_delay=0.1,processing_flags="all")

    # def connect_marker_stream(self):
    #     logger.info(f'Connecting to marker stream "{self.marker_stream_name}".')
    #     self.input_mrk_sw = StreamWatcher(self.marker_stream_name, buffer_size_s=self.buffer_size_s, logger=logger)
    #     self.input_mrk_sw.connect_to_stream()
    #     if len(self.input_mrk_sw.channel_names) != 1:
    #         logger.error("The marker stream should have exactly one channel.")
    #         return 1
    #     return 0

    # def connect_data_stream(self):
    #     logger.info(f'Connecting to data stream "{self.data_stream_name}".')
    #     self.input_sw = StreamWatcher(self.data_stream_name, buffer_size_s=self.buffer_size_s, logger=logger)
    #     self.input_sw.connect_to_stream()

    #     self.input_sfreq = int(self.input_sw.inlet.info().nominal_srate())
    #     self.input_chs_info = [dict(ch_name=ch_name, type="EEG") for ch_name in self.input_sw.channel_names]
    #     print(1)
    #     if self.selected_channels is None:
    #         self.selected_ch_idx = list(range(len(self.input_chs_info)))
    #     else:
    #         if isinstance(self.selected_channels[0], str):
    #             self.selected_ch_idx = [
    #                 self.input_sw.channel_names.index(ch)
    #                 for ch in self.selected_channels
    #             ]
    #         elif isinstance(self.selected_channels[0], int):
    #             self.selected_ch_idx = self.selected_channels
    #         else:
    #             raise logger.error(f"{self.selected_channels=} must be a list of `str` or `int` or `None`.")
    #         return 1

    #     return 0

    def check_if_decoding_should_start(self):
        if self.input_mrk_sw is None:
            logger.error("No marker stream connected, cannot start decoding based on markers.")

        if self.input_mrk_sw.n_new > 0:
            markers = self.input_mrk_sw.unfold_buffer()[-self.input_mrk_sw.n_new:, 0]
            markers_t = self.input_mrk_sw.unfold_buffer_t()[-self.input_mrk_sw.n_new:]

            if self.start_eval_marker in markers:
                logger.debug(f"Starting decoding based on marker '{self.start_eval_marker}'")
                self.is_decoding = True
                self.input_mrk_sw.n_new = 0
                self.internal_decoding_start_time = time.time()

                # get time stamp of start_eval_marker --> consider inputs for epoch from this onwards
                idx = np.where(markers == self.start_eval_marker)[0]
                self.start_eval_time = markers_t[idx]

    def has_decoding_event(self) -> bool:
        """
        Check if the LSL stream contained a `stimulation_presented` marker.
        """

        #remember number of samples before update of sw
        n_samples = self.decoder_sw.n_new 
        self.decoder_sw.update()

        if self.decoder_sw.n_new > n_samples: #check if new data has arived
            return True

        return False

    def create_filterbank(self):
        logger.info("Creating the classifier and the filter bank.")
        assert self.input_chs_info, (
            f"self.input_chs_info is {self.input_chs_info}. Please connect to "
            "the input lsl stream to derive channel information by calling "
            " `self.connect_data_stream()`"
        )
        self.filterbank = FilterBank(
            bands={"band": self.band},
            sfreq=self.input_sfreq,
            output="signal",
            n_in_channels=len(self.selected_ch_idx),
            filter_buffer_s=self.buffer_size_s,
        )

    def _filter(self):
        if self.input_sw is None:
            logger.error("No input stream connected, cannot filter input.")

        if self.input_sw.n_new > 0:
            x = self.input_sw.unfold_buffer()[-self.input_sw.n_new:, self.selected_ch_idx]
            t = self.input_sw.unfold_buffer_t()[-self.input_sw.n_new:]
            self.filterbank.filter(x, t)
            self.input_sw.n_new = 0  # makes sure samples are filtered only once

    def _create_epochs(self):
        x = self.input_sw.inlet.do_pull_chunk()
        delta_t = self.input_stream.time_correction()
        markers = self.input_mrk_sw.unfold_buffer()
        print(markers)

    def _create_epoch(self) -> NDArray:
        # x = self.filterbank.get_data()[:, :, 0]
        x = self.input_sw.unfold_buffer()
        t = self.input_sw.unfold_buffer_t()
        # Find marker onset timepoint
        idx = np.argmin(np.abs(t - self.start_eval_time))

        # Add padding interval to catch filtering artefacts
        if self.padding_size_s is not None and self.padding_size_s > 0:
            pad = int(self.input_sfreq * self.padding_size_s)
            idx -= pad
            logger.debug(f"Added {pad} samples padding to catch filter artfacts")

        # Select trial relevant data
        x = x[idx:, :].T[None, :, :]  # (1, n_channels, n_samples)
        logger.debug(f"Created epoch of shape {x.shape} (n_trials x n_channels x n_samples).")

        if np.isnan(x).sum() > 0:
            logger.error("NaNs found after epoching.")

        return x

    def _resample(self, x: NDArray) -> NDArray:

        if self.classifier_input_sfreq is not None:
            logger.debug(f"The data x is of shape {x.shape} (n_trials x n_channels x n_samples) before resample.")
            x = resample(
                x,
                num=int(x.shape[2] / self.input_sfreq * self.classifier_input_sfreq),
                axis=2,
            )
            logger.debug(f"The data x is of shape {x.shape} (n_trials x n_channels x n_samples) after resample.")

            # Remove padding interval to catch filtering artefacts
            if self.padding_size_s is not None and self.padding_size_s > 0:
                pad = int(self.classifier_input_sfreq * self.padding_size_s)
                x = x[:, :, pad:]
                logger.debug(f"Removed {pad} samples padding to catch filter artfacts")

            if np.isnan(x).sum() > 0:
                logger.error("NaNs found after resampling")

        return x

    # def epoch(self):
    #     epoch = []
    #     x = self.input_sw.unfold_buffer
    #     if self.input_mrk_sw.n_new > 0:
    #                 markers = self.input_mrk_sw.unfold_buffer()[-self.input_mrk_sw.n_new:, 0]
    #                 markers_t = self.input_mrk_sw.unfold_buffer_t()[-self.input_mrk_sw.n_new:]
    #     for i in range(len(markers)):
    #         if markers[i] != 0.0:
    #             epoch.append()





    def run(self):
        """Retrieve input buffer, process data, compute average and push to LSL decoder stream """
        evoked = None
        logger.debug(f"Updating the decoder - {self.is_decoding=}")
        while True:
            self.is_decoding = True
            # self.input_sw.update()
            # self.input_mrk_sw.update()
            # print(self.input_mrk_sw.unfold_buffer())
            # self._create_epochs()
            # self.check_if_decoding_should_start()
            if self.is_decoding:
                # x = self._create_epoch()
                # print(self.input_mrk_stream.ch_names)
                # print(self.epochstream.n_new_epochs)
                if self.epochstream.n_new_epochs == 0:
                            continue  # nothing new to do
                print("entered")
                n = 1
                logger.info("Got %s / %s new epochs.", self.epochstream.n_new_epochs, n)
                n += self.epochstream.n_new_epochs

                data = self.epochstream.get_data(n_epochs=self.epochstream.n_new_epochs)
                new_evoked = EvokedArray(
                    np.average(data, axis=0), self.epochstream.info, nave=data.shape[0]
                )
                evoked = (
                    new_evoked
                    if evoked is None
                    else combine_evoked([evoked, new_evoked], weights="nave")
                )
                global X
                X= evoked.get_data()
                # print(evoked.get_data())
                # print(evoked.get_data().shape)
                self.outlet.push_sample(evoked.get_data().flatten())
            else:
                logger.info("Waiting for decoding to start")

#End of class
def visualisation_factory(config_path: Path = Path("./configs/config.toml")):

    """Factory function to create an Visualisation object from a config file."""
    cfg = toml.load(config_path)

    decoder = Visualisation(
        marker_stream_name=cfg["streams"]["marker_stream_name"],
        data_stream_name=cfg["streams"]["data_stream_name"],
        decoder_stream_name=cfg["streams"]["decoder_stream_name"],
        buffer_size_s=cfg["streams"]["buffer_size_s"],
        padding_size_s=cfg["streams"]["padding_size_s"],
        start_eval_marker=cfg["streams"]["start_eval_marker"],
        max_eval_time_s=cfg["online"]["max_eval_time_s"],
        selected_channels=cfg["data"].get("selected_channels", None),
        output_port=cfg["visualisation"]["output_port"],
        output_address=cfg["visualisation"]["output_address"],
        band = cfg["data"]["passband_hz"]
    )
    return decoder

def cli_run():
    decoder = visualisation_factory(Path("./configs/config.toml"))
    decoder.init_all()
    

if __name__ == "__main__":
    Fire(cli_run())
