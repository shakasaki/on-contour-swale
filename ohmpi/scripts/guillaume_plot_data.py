import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os

datadir = './data/20250518/'


fnames = os.listdir(datadir)
print(fnames)

# only take zip files and unzip them
fnames = [f for f in fnames if f.endswith('.zip')]
for fname in fnames:
    os.system('unzip ' + datadir + fname)

fnames = os.listdir('.')
fnames = [f for f in fnames if f.endswith('_fw.csv')]



df = pd.read_csv(fnames[1])
tracedic = {}
for key, sdf in df.groupby(['a', 'b', 'm', 'n']):
    tracedic[' '.join([str(a) for a in key])] = sdf


# In[33]:


# for key in list(tracedic.keys())[10:30]:
#     sdf = tracedic[key]
#     fig, axs = plt.subplots(2, 1, sharex=True)
#     ax = axs[0]
#     ax.set_title(key)
#     ax.plot(sdf['t'], sdf['current'], 'r.-')
#     ax.set_ylabel('Iab [mA]')
#     ax = axs[1]
#     ax.plot(sdf['t'], sdf['voltage'], '.-')
#     ax.set_ylabel('Vmn [mV]')
#     ax.set_xlabel('Time [s]')


# In[34]:


# import bokeh from here as it masks some other variables
from bokeh.models import (ColumnDataSource, Div, Paragraph, TabPanel, Tabs,
Select, CustomJS, LogColorMapper, LinearColorMapper, Label, LabelSet,
DatetimeTickFormatter, Range1d)
from bokeh.transform import linear_cmap, log_cmap
from bokeh.plotting import figure, show, save, output_file, output_notebook
from bokeh.layouts import column, row

output_notebook()
output_file('ohmpi-india.html')


# In[35]:


# interactive apparent pseudo-sections
sourcedic = {}
keys = []
for key in tracedic:
    keys.append(key)
    sdf = tracedic[key]
    sourcedic[key] = {
        't': sdf['time'].tolist(),
        'current': sdf['current'].tolist(),
        'voltage': sdf['voltage'].tolist()
    }
source = ColumnDataSource(data=sourcedic[keys[0]])

fig1 = figure(width=800, height=200)
fig1.xaxis.axis_label = 'Time [s]'
fig1.yaxis.axis_label = 'Iab [mA]'
fig1.line(x='t', y='current', source=source,
          line_color='red')

fig2 = figure(width=800, height=200)
fig2.xaxis.axis_label = 'Time [s]'
fig2.yaxis.axis_label = 'Vmn [mV]'
fig2.line(x='t', y='voltage', source=source,
          line_color='blue')

# select menu
keys = list(tracedic.keys())
select = Select(title="Quadrupole:", value=keys[0], options=keys)
select.js_on_change("value", CustomJS(
    args={'source': source, 'sourcedic': sourcedic},
    code="""
    console.log(this.value);
    console.log(sourcedic[this.value])
    let dic = sourcedic[this.value]
    source.data = {
        't': dic['t'],
        'current': dic['current'],
        'voltage': dic['voltage']
    }
    
"""))

show(column(select, fig1, fig2))


