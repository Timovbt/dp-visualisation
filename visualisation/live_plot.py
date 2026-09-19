import dash
import plotly
import plotly.express as px
import numpy as np
import plotly.graph_objs as go
from dash.dependencies import Output, Input
from dash import html
from dash import dcc
from waitress import serve
from visualisation.utils.logging import logger
from mne_lsl.lsl import StreamInlet,resolve_streams

"""Script to initialize a Dash server on which to show Plotly plot"""


TIME = np.arange(-200,500,10) 
data_stream = None

app = dash.Dash(__name__)
app.layout = html.Div(
    [
        dcc.Graph(id = 'live-graph', animate = False),
        dcc.Interval(
            id = 'graph-update',
            interval = 1000,
            n_intervals = 0
        ),
    ]
)

@app.callback(
    Output('live-graph', 'figure'),
    [ Input('graph-update', 'n_intervals') ]
)
def update_graph(n):
    """
    Function to update the graph with new data from the LSL stream, 
    this function is automatically called by the dash server
    """
    channels = 3
    custom_theme = dict(
    layout=go.Layout()
    )
    if data_stream != None:
        buf_data = data_stream.pull_sample()
        print(buf_data[0].shape)
        N = buf_data[0][0] #number of epochs used for average
        EEG_average = buf_data[0][1:].reshape(channels,70) 
        print((EEG_average.shape))
        fig = px.line(
                x=TIME, #name='Scatter',
                y=list(EEG_average[1,:70]),
                template=custom_theme,
                title = f"Number of epochs {int(N)}"
                #mode= 'lines'
        ).update_layout(
        xaxis_title="Time (ms)", yaxis_title="\u03bcV"
        )#.update_traces(line_color="#181896")
        fig.add_vline(0, line_color='red')
        fig.add_scatter(x=TIME,y=list(EEG_average[2,:70]),mode='lines')

        return fig #{'data': [data],
                #    'layout' : go.Layout(xaxis=dict(range=[TIME[0],TIME[-1]]),yaxis = dict(range = [min(EEG_average[0,:70]),max(EEG_average[0,:70])]),title=title)}

def connect_stream():
    global data_stream
    streams = resolve_streams(name='output_average_stream')
    if len(streams) > 0:
        data_stream = StreamInlet(streams[0])
    else:
        data_stream = None
    logger.info("No data-stream found")

    if data_stream != None:
        data_stream.open_stream()

def run_plot(host='127.0.0.1',port=8088):
    """start the server and show the plot
    params:
    host: str 
        address for the dash server (default localhost)
    port: int
        output port for the dash server
    """
    connect_stream()
    serve(app,host=host,port=port)

if __name__ == "__main__":
    connect_stream()
    serve(app, host='127.0.0.1', port=8088)
