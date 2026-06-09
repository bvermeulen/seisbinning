"""
binning application
conventions:
azimuth zero -
    source increase with x axis
    receivers increase with y axis

azimuth 90 -
    source decrease with y axis
    receivers increase with x axis
    use negative source_bin_interval to have source to increase with y axis
"""

import time
from pathlib import Path
import pandas as pd
import math
from sqlalchemy import create_engine, text
from bins import read_config, calc_bin_index

BATCH_SIZE = 10_000
config = read_config()
bin_files_stem = config["bin_files_stem"]
azimuth = config["azimuth"]
origin = (config["easting"], config["northing"], azimuth)
bin_size = (config["bin_sp_int"], config["bin_rp_int"])


class Binning:
    def __init__(self):
        db_file = "sqlite:///" + bin_files_stem + "_bins.sqlite"
        self.table = "traces"
        self.engine = create_engine(db_file)
        self.create_traces_table()

    def create_traces_table(self):
        with self.engine.connect() as connection:
            query = text(f"DROP TABLE IF EXISTS {self.table}")
            connection.execute(query)
            connection.commit()

        with self.engine.connect() as connection:
            sql_string = text(
                f"CREATE TABLE {self.table} ("
                f"id INTEGER PRIMARY KEY, "
                f"src_line REAL, "
                f"src_point REAL, "
                f"src_index INTEGER, "
                f"rcv_line REAL, "
                f"rcv_point REAL, "
                f"rcv_index INTEGER, "
                f"mid_point_x DOUBLE PRECISION, "
                f"mid_point_y DOUBLE PRECISION, "
                f"offset REAL, "
                f"azimuth REAL, "
                f"bin_sp INTEGER, "
                f"bin_rp INTEGER "
                f");"
            )
            connection.execute(sql_string)
            connection.commit

    def parse_sps_rcv(self) -> pd.DataFrame:
        sps_rcv_file = Path(bin_files_stem + ".R")
        with open(sps_rcv_file, mode="rt") as file:
            lines = file.readlines()

        rcv_dict = {
            "type": [],
            "line": [],
            "point": [],
            "p_index": [],
            "easting": [],
            "northing": [],
            "elevation": [],
        }
        for line in lines:
            if line[0] != "R":
                continue

            rcv_dict["type"].append(line[0])
            rcv_dict["line"].append(float(line[1:12]))
            rcv_dict["point"].append(float(line[12:22]))
            rcv_dict["p_index"].append(int(line[22:25]))
            rcv_dict["easting"].append(float(line[46:56]))
            rcv_dict["northing"].append(float(line[56:66]))
            rcv_dict["elevation"].append(
                (float(line[66:75]) if line[66:75].replace(" ", "") else 0.0)
            )

        rcv_df = pd.DataFrame(rcv_dict)
        return rcv_df

    def parse_sps_src(self) -> pd.DataFrame:
        sps_src_file = Path(bin_files_stem + ".S")
        with open(sps_src_file, mode="rt") as file:
            lines = file.readlines()

        src_dict = {
            "type": [],
            "line": [],
            "point": [],
            "p_index": [],
            "easting": [],
            "northing": [],
            "elevation": [],
        }
        for line in lines:
            if line[0] != "S":
                continue

            p_index = line[22:25].strip()
            if p_index[-2:] == "KL":
                continue

            else:
                p_index = int(p_index[0:1])

            src_dict["type"].append(line[0])
            src_dict["line"].append(float(line[1:12]))
            src_dict["point"].append(float(line[12:22]))
            src_dict["p_index"].append(p_index)
            src_dict["easting"].append(float(line[46:56]))
            src_dict["northing"].append(float(line[56:66]))
            src_dict["elevation"].append(
                (float(line[66:75]) if line[66:75].replace(" ", "") else 0.0)
            )

        src_df = pd.DataFrame(src_dict)
        return src_df

    def parse_sps_x(self) -> pd.DataFrame:
        sps_x_file = Path(bin_files_stem + ".X")
        with open(sps_x_file, mode="rt") as file:
            lines = file.readlines()

        x_dict = {
            "type": [],
            "src_line": [],
            "src_point": [],
            "src_index": [],
            "chan_start": [],
            "chan_end": [],
            "chan_incr": [],
            "rcv_line": [],
            "rcv_point_start": [],
            "rcv_point_end": [],
            "rcv_index": [],
            "tb": [],
        }
        for line in lines:
            if line[0] != "X":
                continue

            x_dict["type"].append(line[0])
            x_dict["src_line"].append(float(line[17:27]))
            x_dict["src_point"].append(float(line[27:37]))
            x_dict["src_index"].append(int(line[37:38]))
            x_dict["chan_start"].append(int(line[38:43]))
            x_dict["chan_end"].append(int(line[43:48]))
            x_dict["chan_incr"].append(int(line[48:49]))
            x_dict["rcv_line"].append(float(line[49:59]))
            x_dict["rcv_point_start"].append(float(line[59:69]))
            x_dict["rcv_point_end"].append(float(line[69:79]))
            x_dict["rcv_index"].append(int(line[79:80]))
            x_dict["tb"].append(line[80:100])

        x_df = pd.DataFrame(x_dict)
        return x_df

    def save_dataframe(self, df: pd.DataFrame, filename: Path):
        df.to_parquet(filename)

    def traces(
        self, rcv_df: pd.DataFrame, src_df: pd.DataFrame, x_df: pd.DataFrame
    ) -> pd.DataFrame:

        trace_count = 0
        x_dict = x_df.to_dict(orient="records")
        for i, x_row in enumerate(x_dict):
            src_line = x_row["src_line"]
            src_point = x_row["src_point"]
            src_index = x_row["src_index"]
            if i % BATCH_SIZE == 0:
                if i != 0:
                    traces_df = pd.DataFrame(traces_dict)
                    traces_df.to_sql(
                        name=self.table,
                        con=self.engine,
                        if_exists="append",
                        index=False,
                    )
                traces_dict = {
                    "src_line": [],
                    "src_point": [],
                    "src_index": [],
                    "rcv_line": [],
                    "rcv_point": [],
                    "rcv_index": [],
                    "mid_point_x": [],
                    "mid_point_y": [],
                    "offset": [],
                    "azimuth": [],
                    "bin_sp": [],
                    "bin_rp": [],
                }
                print(
                    f"{i=:06}, {src_line=}, {src_point=}, {src_index=}, {trace_count=:,}"
                )

            selected_src_df = src_df[
                (src_df.line == src_line)
                & (src_df.point == src_point)
                & (src_df.p_index == src_index)
            ]
            src_easting = float(selected_src_df.easting.iloc[0])
            src_northing = float(selected_src_df.northing.iloc[0])
            rcv_line = x_row["rcv_line"]
            rcv_point_start = x_row["rcv_point_start"]
            rcv_point_end = x_row["rcv_point_end"]
            rcv_index = x_row["rcv_index"]
            filter_rcv_by_line_df = rcv_df[
                (rcv_df.line == rcv_line)
                & rcv_df.point.between(rcv_point_start, rcv_point_end)
                & (rcv_df.p_index == rcv_index)
            ]
            rcv_dict = filter_rcv_by_line_df.to_dict(orient="records")
            for rcv_row in rcv_dict:
                mid_point_x = (src_easting + rcv_row["easting"]) * 0.5
                mid_point_y = (src_northing + rcv_row["northing"]) * 0.5
                dx = rcv_row["easting"] - src_easting
                dy = rcv_row["northing"] - src_northing
                bin_sp, bin_rp = calc_bin_index(
                    mid_point_x, mid_point_y, origin, bin_size[0], bin_size[1]
                )
                azimuth = math.degrees(math.atan2(dy, dx))
                offset = math.sqrt(dx * dx + dy * dy)
                traces_dict["src_line"].append(src_line)
                traces_dict["src_point"].append(src_point)
                traces_dict["src_index"].append(src_index)
                traces_dict["rcv_line"].append(rcv_row["line"])
                traces_dict["rcv_point"].append(rcv_row["point"])
                traces_dict["rcv_index"].append(rcv_index)
                traces_dict["mid_point_x"].append(mid_point_x)
                traces_dict["mid_point_y"].append(mid_point_y)
                traces_dict["offset"].append(offset)
                traces_dict["azimuth"].append(azimuth)
                traces_dict["bin_sp"].append(bin_sp)
                traces_dict["bin_rp"].append(bin_rp)
                trace_count += 1

        # handle the last incomplete batch of traces
        traces_df = pd.DataFrame(traces_dict)
        traces_df.to_sql(
            name=self.table, con=self.engine, if_exists="append", index=False
        )
        print(f"{trace_count=:,}")


def main():
    s2d = Binning()
    rcv_df = s2d.parse_sps_rcv()
    s2d.save_dataframe(rcv_df, Path(bin_files_stem + "_rcv.parquet"))
    src_df = s2d.parse_sps_src()
    s2d.save_dataframe(src_df, Path(bin_files_stem + "_src.parquet"))
    x_df = s2d.parse_sps_x()
    s2d.save_dataframe(x_df, Path(bin_files_stem + "_x.parquet"))

    t1 = time.time_ns()
    s2d.traces(rcv_df, src_df, x_df)
    t2 = time.time_ns()
    print(f"trace creation, duration: {(t2 - t1) * 1e-9 / 60:.2f} minutes")


if __name__ == "__main__":
    main()
