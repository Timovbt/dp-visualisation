# Just wrap the code with fire to also have a CLI
import numpy as np
import time
from fire import Fire
from dareplane_utils.stream_watcher.lsl_stream_watcher import StreamWatcher
from dareplane_utils.general.time import sleep_s
from dareplane_utils.signal_processing.filtering import FilterBank
from pylsl import StreamInlet
from visualisation.utils.logging import logger
from visualisation.live_plot import Live_plot
from numpy.typing import NDArray
from scipy.signal import resample


#config: buffer_size_s, decoder_stream_name,port,address

class Visualisation():
    """
    Object to decode LSL-stream and send analysed data to Live_plot

    Parameters
    ----------

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
            t_sleep_s: float = 0.1,
            selected_channels: list[str] | None = None,
            ):
        
        self.marker_stream_name = marker_stream_name
        self.data_stream_name = data_stream_name
        self.decoder_stream_name = decoder_stream_name
        self.buffer_size_s = buffer_size_s
        self.padding_size_s = padding_size_s
        self.start_eval_marker = start_eval_marker
        self.t_sleep_s = t_sleep_s
        self.selected_channels = selected_channels

        self.selected_ch_idx = None
        self.is_decoding: bool = False
        self.start_eval_time: float = 0.0
        self.internal_decoding_start_time: float = time.time()
        self.classifier = None
        self.classifier_meta = None

        self.input_mrk_sw: StreamWatcher | None = None
        self.input_sw: StreamWatcher | None = None
        self.input_sfreq: int | None = None
        self.input_chs_info: list[dict[str, str]] | None = None
        self.filterbank: FilterBank | None = None
        self.output_sw: StreamWatcher | None = None
        self.band = None
        self.classifier_input_sfreq = None
        #TODO preprocess lsl stream data

        self.figure = 0 #implement figure
        self.connect_to_decoder_lsl_stream()
        
        self.figure = Live_plot(logger=logger,
                                port=0,
                                address=0)

    def connect_to_decoder_lsl_stream(self) -> None:
            name = self.cfg["streams"]["decoder_stream_name"]
            logger.info(f'Connecting to decoder stream "{name}".')
            self.decoder_sw = StreamWatcher(name=name,buffer_size_s=self.cfg['streams']['buffer_size_s'])
            self.decoder_sw.connect_to_stream()

    def connect_marker_stream(self):
        logger.info(f'Connecting to marker stream "{self.marker_stream_name}".')
        self.input_mrk_sw = StreamWatcher(self.marker_stream_name, buffer_size_s=self.buffer_size_s, logger=logger)
        self.input_mrk_sw.connect_to_stream()

        if len(self.input_mrk_sw.channel_names) != 1:
            logger.error("The marker stream should have exactly one channel.")
            return 1

        return 0

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

    def update_figure(self):
        X = self.decoder_sw.buffer.average() ##untested
        self.figure.update(X)

    def _filter(self):
        if self.input_sw is None:
            logger.error("No input stream connected, cannot filter input.")

        if self.input_sw.n_new > 0:
            x = self.input_sw.unfold_buffer()[-self.input_sw.n_new:, self.selected_ch_idx]
            t = self.input_sw.unfold_buffer_t()[-self.input_sw.n_new:]
            self.filterbank.filter(x, t)
            self.input_sw.n_new = 0  # makes sure samples are filtered only once

    def _create_epoch(self) -> NDArray:
        x = self.filterbank.get_data()[:, :, 0]
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

#End of class

def start_visualisation():
     pass

if __name__ == "__main__":
    Fire(start_visualisation())
