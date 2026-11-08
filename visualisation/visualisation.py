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
            t_sleep_s: float = 0.1,
            selected_channels: list | None = None,
            selected_channel_names: list[str]| None= None,
            output_port: int=8088,
            output_address:str="127.0.0.1",
            band: list[int] = [6,40],
            oddball:int = 0
            ):
        
        self.marker_stream_name = marker_stream_name
        self.data_stream_name = data_stream_name
        self.decoder_stream_name = decoder_stream_name
        self.buffer_size_s = buffer_size_s
        self.padding_size_s = padding_size_s
        self.start_eval_marker = start_eval_marker
        self.t_sleep_s = t_sleep_s
        self.selected_channels = selected_channels
        self.selected_channel_names = selected_channel_names
        self.output_port = output_port
        self.output_address = output_address
        self.band = band
        self.oddball = oddball

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
        self.evoked = None
        self.evoked_std = None
        self.evoked_non_target = None
        self.evoked_Target = None
        self.reset = False
        self.stack = None
        

    def init_all(self) -> int:
        """Returns an int as this is exposed as a PCOMM `CONNECT_DECODER`"""

        logger.info("initializing decoder")
        self.connect_marker_stream()
        self.connect_data_stream()
        self.connect_output_stream()
        self.connect_epoch_stream()
        # self.create_filterbank()
        self.plot()
        if self.oddball:
            self.run_ODDBALL()
        else:
            self.run()

        return 0

    def plot(self):
        import subprocess
        subprocess.Popen(['python','-m', 'visualisation.live_plot'],shell=True)

    def connect_output_stream(self):
        info = StreamInfo(
                            name=self.decoder_stream_name,
                            type="data",
                            channel_count=2 * 280 * len(self.selected_channels) + 4,
                            channel_format=pylsl.cf_float32,
                            source_id="output_average_stream",
                        )
        
        channels = info.desc().append_child("channels")
        for i in self.channel_names:
            channels.append_child_value('channel',i)


        self.outlet = StreamOutlet(info) #outlet for processed data

    def connect_epoch_stream(self):
         if self.input_mrk_stream != None and self.input_stream != None:
            self.epochstream = EpochsStream(
                            stream = self.input_stream,
                            bufsize = 2,
                            event_id= {'VEP':1,"odd":2,"reset":3},
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
        self.input_stream.filter(self.band[0],self.band[1])

        names = self.selected_channel_names
        self.channel_names = names if names != None else [str(i) for i in range((self.input_stream.sinfo.n_channels))]
        self.n_channels = self.input_stream.sinfo.n_channels
        self.n_channels_arr = np.array([len(self.selected_channels)])


    def run(self):
        """Retrieve input buffer, process data, compute average and push to LSL decoder stream """
        logger.debug(f"Updating the decoder - {self.is_decoding=}")
        self.n = 0
        self.sum_squared = 0 
        self.sum_x = None
        self.reset = np.array([0])
        while True:
            if self.epochstream.n_new_epochs == 0:
                        continue  # nothing new to do
            # print(self.epochstream.events)
            if 3 in self.epochstream.events[-(self.epochstream.n_new_epochs+2):]:
                            self.evoked = None
                            self.n = 0
                            self.reset[0] = 1 
                            logger.info("RESET")
            logger.info("Got %s new epochs.", self.epochstream.n_new_epochs)
            self.n += self.epochstream.n_new_epochs
            data = self.epochstream.get_data(n_epochs=self.epochstream.n_new_epochs)
            # print(data.shape)
            epoch_average = EvokedArray(np.average(data, axis=0), self.epochstream.info, nave=data.shape[0]).resample(400) #.filter(self.band[0],self.band[1])
            self.evoked = (epoch_average if self.evoked is None else combine_evoked([self.evoked, epoch_average], weights="nave"))

            self.stack = (data if self.stack is None else np.concatenate((self.stack,data),axis=0))
            self.evoked_std = EvokedArray(np.std(self.stack,axis=0),self.epochstream.info,nave=data.shape[0]).resample(400)

            self.n = np.array([self.evoked.nave])
            self.average = self.evoked.get_data()

            self.outlet.push_sample(np.concat((self.n,self.n_channels_arr,self.reset,np.array([self.oddball]),self.average.flatten(),self.evoked_std.get_data().flatten()),axis=0))
            self.reset[0] = 0


    def run_ODDBALL(self):
        """Retrieve input buffer, process data, compute average of target en non-target and push to LSL decoder stream """
        logger.debug(f"Updating the decoder - {self.is_decoding=}")
        self.n = 0
        self.sum_squared = 0 
        self.sum_x = None
        self.reset = np.array([0])
        while True:
            if self.epochstream.n_new_epochs == 0:
                        continue  # nothing new to do
            print(self.epochstream.events)
            if 3 in self.epochstream.events[-(self.epochstream.n_new_epochs+2):]:
                            self.evoked = None
                            self.n = 0
                            self.reset[0] = 1 
                            logger.info("RESET")


            logger.info("Got %s new epochs.", self.epochstream.n_new_epochs)
            # self.n += self.epochstream.n_new_epochs

            data = self.epochstream.get_data(n_epochs=self.epochstream.n_new_epochs)
            event = self.epochstream.events[-1]
        
            if event == 1:
                epoch_average = EvokedArray(np.average(data, axis=0), self.epochstream.info, nave=data.shape[0]).resample(400)
                self.evoked_Target = (epoch_average if self.evoked_Target is None else combine_evoked([self.evoked_Target, epoch_average], weights="nave"))
                self.average_T = self.evoked_Target.get_data()
                self.n = self.evoked_Target.nave
                if self.evoked_non_target is None:  
                    self.average_NT = np.zeros(shape=self.average_T.shape)         
            if event == 2:
                epoch_average = EvokedArray(np.average(data, axis=0), self.epochstream.info, nave=data.shape[0]).resample(400) 
                self.evoked_non_target = (epoch_average if self.evoked_non_target is None else combine_evoked([self.evoked_non_target, epoch_average], weights="nave"))
                self.average_NT = self.evoked_non_target.get_data()
                if self.evoked_Target is None:
                     self.average_T = np.zeros(shape=self.average_NT.shape)
                     
           #np.array([self.evoked_non_target.nave + self.evoked_target.nave])
            # self.average = self.evoked.get_data()

            self.outlet.push_sample(np.concat((np.array([self.n]),
                                               self.n_channels_arr,
                                               self.reset,
                                               np.array([self.oddball]),
                                               self.average_T.flatten(),
                                               self.average_NT.flatten()
                                               ),axis=0))
            self.reset[0] = 0


    def set_oddball(self):
        self.oddball = 1 if self.oddball == 0 else 0
        print(f'oddball: {self.oddball}')
        return 0
    def reset(self):
        """
        Reset the running average
        """
        self.reset = True

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
        selected_channels=cfg["data"].get("selected_channels", None),
        selected_channel_names=cfg['data'].get("selected_channel_names", None),
        output_port=cfg["visualisation"]["output_port"],
        output_address=cfg["visualisation"]["output_address"],
        band = cfg["data"]["passband_hz"],
        oddball = False
    )
    return decoder

def cli_run():
    decoder = visualisation_factory(Path("./configs/config.toml"))
    decoder.init_all()
    

if __name__ == "__main__":
    Fire(cli_run())
