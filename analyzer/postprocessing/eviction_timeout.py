import pandas as pd
from matplotlib import pyplot as plt
import numpy as np
import sys

if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)

dataframe = pd.read_csv(sys.argv[1])
print(dataframe.head())

groups = dataframe.groupby("us_between_measurements")
columns_first = []
columns_second = []
ticks = []
for val, grp in groups:
    ticks.append(val / 1_000_000)
    columns_first.append(grp["us_latency1"])
    columns_second.append(grp["us_latency2"])

def set_box_color(bp, color):
    plt.setp(bp['boxes'], color=color)
    plt.setp(bp['whiskers'], color=color)
    plt.setp(bp['caps'], color=color)
    plt.setp(bp['medians'], color=color)


bf = plt.boxplot(columns_first, positions=np.array(range(len(columns_first)))*2.0-0.4, sym='', widths=0.6)
bs = plt.boxplot(columns_second, positions=np.array(range(len(columns_first)))*2.0+0.4, sym='', widths=0.6)
set_box_color(bf, '#D7191C')
set_box_color(bs, '#2C7BB6')

# draw temporary red and blue lines and use them to create a legend
plt.plot([], c='#D7191C', label='first ping rtt')
plt.plot([], c='#2C7BB6', label='second ping rtt')
plt.legend()

plt.xticks(range(0, len(ticks) * 2, 2), ticks)
plt.tight_layout()

plt.xlabel("delay between pings")
plt.ylabel("round trip time in μs")

plt.show()


