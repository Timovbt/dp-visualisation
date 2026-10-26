import dash
import plotly
import threading
import plotly.express as px
import numpy as np
import toml
import plotly.graph_objs as go
from pathlib import Path
from dash.dependencies import Output, Input
from dash import html
from dash import dcc
from waitress import serve
from visualisation.utils.logging import logger
from mne_lsl.lsl import StreamInlet,resolve_streams
from visualisation.visualisation import visualisation_factory
"""Script to initialize a Dash server on which to show Plotly plot"""
channel_names = []


TIME = np.arange(-200,500,2.5) 

custom_theme = dict(
    layout=go.Layout()
    )
app = dash.Dash(__name__)

@app.callback(
    Output('live-graph', 'figure'),
    [Input('dropdown_channels','value'),Input('graph-update', 'n_intervals')]
)
def update_graph(selected_channels,n):
    """
    Function to update the graph with new data from the LSL stream, 
    this function is automatically called by the dash server
    """
    print(selected_channels)
    # custom_theme = dict(
    # layout=go.Layout()
    # )
    global custom_theme
    if data_stream != None:
        buf_data = data_stream.pull_sample()
        if buf_data[0].shape[0] > 0:
            N = buf_data[0][0] #number of epochs used for average
            n_channels = int(buf_data[0][1])
            EEG_average = buf_data[0][2:(280*n_channels)+2].reshape(n_channels,280)
            EEG_std = buf_data[0][2+(n_channels*280):].reshape(n_channels,280)

            if type(selected_channels) == int: #when only 1 selected
                    selected_channels = [selected_channels]

            fig = px.line(
                    x=TIME, #name='Scatter',
                    y=list(EEG_average[selected_channels[0],:]),
                    template=custom_theme,
                    title = f"Number of epochs {int(N)}"
                    #mode= 'lines'
            ).update_layout(
            xaxis_title="Time (ms)", yaxis_title="\u03bcV",
            legend=dict(font=dict(size=16))
            )

            fig.add_vline(0, line_color='black',line_width=3)

            if len(selected_channels) > 1:
                for i in selected_channels:
                    fig.add_scatter(x=TIME,
                                    y=list(EEG_average[i,:]),
                                    mode='lines',name=channel_names[i])
                    # fig.add_scatter(x=TIME,
                    #                 y=list(EEG_average[i,:] + EEG_std[i,:]),
                    #                 mode='lines',line={'width':1})
                    # fig.add_scatter(x=TIME,
                    #                 y=list(EEG_average[i,:] - EEG_std[i,:]),
                    #                 mode='lines',fill="tonexty",line={'width':1})

            return fig 

def connect_stream():
    global data_stream
    global channel_names
    streams = resolve_streams(name='output-average-stream')
    if len(streams) > 0:
        data_stream = StreamInlet(streams[0])
    else:
        data_stream = None
    logger.info("No data-stream found")

    if data_stream != None:
        data_stream.open_stream()
        info = data_stream.get_sinfo().desc

        _channels = info.child("channels")
        channel = _channels.child("channel")

        while not channel.empty():
            channel_names.append(channel.first_child().value())
            next_channel = channel.next_sibling("channel")
            if next_channel.empty():
                break
            channel = next_channel
         
        print(channel_names)
        global channels
        channels = [{'label':name,'value':i} for i,name in enumerate(channel_names)]
    app.layout = html.Div(
    [
        dcc.Graph(id = 'live-graph', animate = False),
        dcc.Interval(
            id = 'graph-update',
            interval = 1000,
            n_intervals = 0
        ),
        dcc.Dropdown( id = 'dropdown_channels',
        options=channels,
        value=0,multi=True
    ),
    ]
)

def run_plot(host='127.0.0.1',port=8088):
    """start the server and show the plot
    params:
    host: str 
        address for the dash server (default localhost)
    port: int
        output port for the dash server
    """
    connect_stream()
    serve(app, host='127.0.0.1', port=8088)
    
if __name__ == "__main__":
    connect_stream()
    serve(app, host='127.0.0.1', port=8088)
