import polars as pl
from matplotlib import pyplot as plt
import matplotlib.patches as mpatches
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

#bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency4'], label="fourth ping", marker=".")

def median_line(lat, width):
    times = []
    medians = []
    q25 = []
    q75 = []
    wmin = []
    wmax = []
    for micros_left, values in rolling_window_left(dataframe["us_since_last_measurement"], dataframe[lat], width):
        medians.append(np.median(values))
        wmin.append(np.quantile(values, 0.05))
        wmax.append(np.quantile(values, 0.95))
        q25.append(np.quantile(values, 0.25))
        q75.append(np.quantile(values, 0.75))
        times.append((micros_left + width/2) / 1000)  # centered
    return times, medians, q25, q75, wmin, wmax

WINDOW = 100_000 # in micros

medTs1, med1, q251, q751, min1, max1 = median_line("us_latency1", WINDOW)
medTs2, med2, q252, q752, min2, max2 = median_line("us_latency2", WINDOW)
medTs3, med3, q253, q753, min3, max3 = median_line("us_latency3", WINDOW)



plt.fill_between(medTs1, min1, max1, alpha=0.1, color="blue")
plt.fill_between(medTs1, q251, q751, alpha=0.4, color="blue")
plt.plot(medTs1, med1, label=f"centered {WINDOW//1000}ms-window median 1", color="blue")
plt.fill_between(medTs2, min2, max2, alpha=0.1, color="orange")
plt.fill_between(medTs2, q252, q752, alpha=0.4, color="orange")
plt.plot(medTs2, med2, label=f"centered {WINDOW//1000}ms-window median 2", color="orange")
plt.fill_between(medTs3, min3, max3, alpha=0.1, color="green")
plt.fill_between(medTs3, q253, q753, alpha=0.4, color="green")
plt.plot(medTs3, med3, label=f"centered {WINDOW//1000}ms-window median 3", color="green")

bf = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency1'], label="first ping", s=0.7, linewidths=0, alpha=0.5)
bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency2'], label="second ping", s=0.7, linewidths=0, alpha=0.5)
bs = plt.scatter(dataframe['us_since_last_measurement'] / 1000, dataframe['us_latency3'], label="third ping", s=0.7, linewidths=0, alpha=0.5)





blue = mpatches.Patch(color='blue', label='1st ping')
orange = mpatches.Patch(color='orange', label='2nd ping')
green = mpatches.Patch(color='green', label='3rd ping')
description2 = mpatches.Patch(color='none', label=f"highlighed 5th, 25th, 50th, 75th and 95th percentiles")
description = mpatches.Patch(color='none', label=f"using {WINDOW//1000}ms-wide rolling window")
plt.legend(handles=[blue, orange, green, description2, description], loc="upper left")
plt.ylim((0, 1800))
#plt.tight_layout()

plt.xlabel("delay between pings (ms)")
plt.ylabel("round trip time in μs")


plt.savefig('/tmp/plot.pdf', bbox_inches="tight")
#plt.show()



