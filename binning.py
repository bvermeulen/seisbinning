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

import sys
import time
from pathlib import Path
import pandas as pd
import math
from sqlalchemy import create_engine, text
from bins import BinCalcs

BATCH_SIZE = 10_000


class Binning:
    def __init__(self, db_file):
        db_uri = "".join(["sqlite:///", str(db_file)])
        self.engine = create_engine(db_uri)
        self._config = self.get_config_from_db()
        origin = (
            self._config["easting_orig"],
            self._config["northing_orig"],
            self._config["azimuth"],
        )
        bin_size = (
            self._config["bin_sp_int"], 
            self._config["bin_rp_int"]
        )
        self.table = "traces"
        self.create_traces_table()
        self.calcs = BinCalcs(origin, bin_size[0], bin_size[1])

    @property
    def config(self):
        return self._config

    def get_config_from_db(self):
        sql = text("select value from seis_config WHERE key = :key;")
        config = {}
        with self.engine.connect() as conn:
            config["file_stem"] = conn.execute(sql, {"key": "file_stem"}).fetchone()[0]
            config["azimuth"] = float(
                conn.execute(sql, {"key": "azimuth"}).fetchone()[0]
            )
            config["easting_orig"] = float(
                conn.execute(sql, {"key": "easting_orig"}).fetchone()[0]
            )
            config["northing_orig"] = float(
                conn.execute(sql, {"key": "northing_orig"}).fetchone()[0]
            )
            config["bin_sp_int"] = int(
                float(conn.execute(sql, {"key": "bin_sp_int"}).fetchone()[0])
            )
            config["bin_rp_int"] = int(
                float(conn.execute(sql, {"key": "bin_rp_int"}).fetchone()[0])
            )
            config["nb_bin_sp"] = int(
                float(conn.execute(sql, {"key": "nb_bin_sp"}).fetchone()[0])
            )
            config["nb_bin_rp"] = int(
                float(conn.execute(sql, {"key": "nb_bin_rp"}).fetchone()[0])
            )
            config["epsg"] = int(
                float(conn.execute(sql, {"key": "epsg"}).fetchone()[0])
            )

        return config

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
                f"src_code VAR(2), "
                f"rcv_line REAL, "
                f"rcv_point REAL, "
                f"rcv_index INTEGER, "
                f"rcv_code VAR(2), "
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
        sps_rcv_file = Path(self.config["file_stem"] + ".R")
        with open(sps_rcv_file, mode="rt") as file:
            lines = file.readlines()

        rcv_dict = {
            "type": [],
            "line": [],
            "point": [],
            "p_index": [],
            "p_code": [],
            "easting": [],
            "northing": [],
            "elevation": [],
        }
        for line in lines:
            if line[0] != "R":
                continue

            if (p_code := line[24:26].strip()) == "KL":
                continue

            rcv_dict["type"].append(line[0:1])
            rcv_dict["line"].append(float(line[1:11]))
            rcv_dict["point"].append(float(line[11:21]))
            rcv_dict["p_index"].append(int(line[21:24]))
            rcv_dict["p_code"].append(p_code)
            rcv_dict["easting"].append(float(line[45:55]))
            rcv_dict["northing"].append(float(line[55:65]))
            rcv_dict["elevation"].append(
                (float(line[65:75]) if line[65:75].replace(" ", "") else 0.0)
            )

        rcv_df = pd.DataFrame(rcv_dict)
        return rcv_df

    def parse_sps_src(self) -> pd.DataFrame:
        sps_src_file = Path(self.config["file_stem"] + ".S")
        with open(sps_src_file, mode="rt") as file:
            lines = file.readlines()

        src_dict = {
            "type": [],
            "line": [],
            "point": [],
            "p_index": [],
            "p_code": [],
            "easting": [],
            "northing": [],
            "elevation": [],
        }
        for line in lines:
            if line[0] != "S":
                continue

            if (p_code := line[24:26].strip()) == "KL":
                continue

            src_dict["type"].append(line[0:1])
            src_dict["line"].append(float(line[1:11]))
            src_dict["point"].append(float(line[11:21]))
            src_dict["p_index"].append(int(line[21:24]))
            src_dict["p_code"].append(p_code)
            src_dict["easting"].append(float(line[45:55]))
            src_dict["northing"].append(float(line[55:65]))
            src_dict["elevation"].append(
                (float(line[66:75]) if line[65:74].replace(" ", "") else 0.0)
            )

        src_df = pd.DataFrame(src_dict)
        return src_df

    def parse_sps_x(self) -> pd.DataFrame:
        sps_x_file = Path(self.config["file_stem"] + ".X")
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
                    "src_code": [],
                    "rcv_line": [],
                    "rcv_point": [],
                    "rcv_index": [],
                    "rcv_code": [],
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
            src_code = selected_src_df.p_code.iloc[0]
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
                rcv_code = rcv_row["p_code"]
                mid_point_x = (src_easting + rcv_row["easting"]) * 0.5
                mid_point_y = (src_northing + rcv_row["northing"]) * 0.5
                dx = src_easting - rcv_row["easting"]
                dy = src_northing - rcv_row["northing"]
                bin_sp, bin_rp = self.calcs.calc_bin_index(mid_point_x, mid_point_y)
                azimuth = math.degrees(math.atan2(dx, dy))
                offset = math.sqrt(dx * dx + dy * dy)
                traces_dict["src_line"].append(src_line)
                traces_dict["src_point"].append(src_point)
                traces_dict["src_index"].append(src_index)
                traces_dict["src_code"].append(src_code)
                traces_dict["rcv_line"].append(rcv_row["line"])
                traces_dict["rcv_point"].append(rcv_row["point"])
                traces_dict["rcv_index"].append(rcv_index)
                traces_dict["rcv_code"].append(rcv_code)
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


def main(argv):
    if len(argv) != 2:
        print("Provide the bins database file as argument!")
    db_file = Path(argv[1])

    s2d = Binning(db_file)
    bin_files_stem = s2d.config["file_stem"]
    rcv_df = s2d.parse_sps_rcv()
    s2d.save_dataframe(rcv_df, bin_files_stem + "_rcv.parquet")
    src_df = s2d.parse_sps_src()
    s2d.save_dataframe(src_df, bin_files_stem + "_src.parquet")
    x_df = s2d.parse_sps_x()
    s2d.save_dataframe(x_df, bin_files_stem + "_x.parquet")

    t1 = time.time_ns()
    s2d.traces(rcv_df, src_df, x_df)
    t2 = time.time_ns()
    print(f"trace creation, duration: {(t2 - t1) * 1e-9 / 60:.2f} minutes")


if __name__ == "__main__":
    main(sys.argv)
