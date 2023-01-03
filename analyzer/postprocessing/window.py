import pandas as pd
from collections import deque


def rolling_window_left(roll_by, roll_what, window_size):
    values = deque([None])

    start = -1  # inclusive
    end = -1  # inclusive


    while end < len(roll_by):
        # advance starting position
        start += 1
        _ = values.popleft()

        # find the end which is just what we want
        while end+1 < len(roll_by) and roll_by[end+1] - roll_by[start] <= window_size:
            end += 1
            values.append(roll_what[end])

        # we might have hit the end
        if end == len(roll_by) - 1:
            break

        yield roll_by[start], values

        
