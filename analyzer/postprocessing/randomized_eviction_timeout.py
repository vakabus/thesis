import polars as pl
from matplotlib import pyplot as plt
import numpy as np
import sys
from window import rolling_window_left

if len(sys.argv) == 1:
    print("missing argument - name of input csv")
    exit(1)

dataframe = pl.read_csv(sys.argv[1])
print(dataframe.head())

above105 = dataframe.filter(pl.col("us_since_last_measurement") > 11_000_000).with_columns([
    (pl.col("us_latency1") - pl.col("us_latency2")).alias("first_second"),
    (pl.col("us_latency2") - pl.col("us_latency3")).alias("second_third"),
    (pl.col("us_latency1") - pl.col("us_latency3")).alias("first_third"),
])
print(above105.describe())

import numpy as np
import scipy.stats
def mean_confidence_interval(data, confidence=0.95):
    a = 1.0 * np.array(data)
    n = len(a)
    m, se = np.mean(a), scipy.stats.sem(a)
    h = se * scipy.stats.t.ppf((1 + confidence) / 2., n-1)
    return m, m-h, m+h

print("95% confidence interval of the mean of the difference", mean_confidence_interval(above105["first_second"]))

dataframe = dataframe.sort("us_since_last_measurement")

plt.figure(figsize=(13, 8), dpi=600)

bf = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency1'], label="first ping", marker=".", alpha=0.5)
bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency2'], label="second ping", marker=".", alpha=0.5)
bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency3'], label="third ping", marker=".", alpha=0.5)
#bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency4'], label="fourth ping", marker=".")

def median_line(lat, width):
    times = []
    medians = []
    for micros_left, values in rolling_window_left(dataframe["us_since_last_measurement"], dataframe[lat], width):
        medians.append(np.median(values))
        times.append((micros_left + width/2) / 1000)  # centered
    return times, medians

plt.plot(*median_line("us_latency1", 200_000), label="centered 200ms-window median 1", color="blue")
plt.plot(*median_line("us_latency2", 200_000), label="centered 200ms-window median 2", color="orange")
plt.plot(*median_line("us_latency3", 200_000), label="centered 200ms-window median 3", color="green")
#plt.plot(*median_line("us_latency4", 200_000), label="100ms window median 2")

# draw temporary red and blue lines and use them to create a legend
plt.legend()


#plt.tight_layout()

plt.xlabel("delay between pings (ms)")
plt.ylabel("round trip time in μs")


#plt.savefig('/tmp/plot.pdf', bbox_inches="tight")
plt.show()



