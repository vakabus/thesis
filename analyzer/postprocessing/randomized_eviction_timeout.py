import pandas as pd
from matplotlib import pyplot as plt
import numpy as np
import sys
from window import rolling_window_left

if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)

dataframe = pd.read_csv(sys.argv[1])
print(dataframe.head())

dataframe.sort_values("us_since_last_measurement", inplace=True)
dataframe.reset_index(drop=True, inplace=True)

bf = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency1'], label="first ping", marker=".")
bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency2'], label="second ping", marker=".")

def median_line(lat, width):
    times = []
    medians = []
    for micros_left, values in rolling_window_left(dataframe["us_since_last_measurement"], dataframe[lat], width):
        medians.append(np.median(values))
        times.append((micros_left + width/2) / 1000)  # centered
    return times, medians

plt.plot(*median_line("us_latency1", 200_000), label="100ms window median 1")
plt.plot(*median_line("us_latency2", 200_000), label="100ms window median 2")

# draw temporary red and blue lines and use them to create a legend
plt.legend()


plt.tight_layout()

plt.xlabel("delay between pings (ms)")
plt.ylabel("round trip time in μs")

plt.show()


