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
from sqlalchemy import create_engine, text, bindparam
from dbase_module import DbGeneral
from bins import DEG2RAD, BinCalcs


class Traces:
    def __init__(self, database_file):
        self.db_general = DbGeneral(database_file)
        self.config = self.db_general.get_config_from_db()
        self.bc = BinCalcs(self.config)
        self.rcv_df = self.db_general.read_sps_df("rcv")
        self.src_df = self.db_general.read_sps_df("src")
        self.x_df = self.db_general.read_sps_df("x")
        self.x_reduced_df = pd.DataFrame()

    def x_subset_on_bin(self, center_bin) -> None:
        bin_easting, bin_northing = self.bc.calc_bin_xy(center_bin[0], center_bin[1])
        src_min_line, src_max_line, src_min_point, src_max_point = (
            self.bc.calc_bin_sp_extent(bin_easting, bin_northing, 5000)
        )

        x_sub_df = self.x_df[
            (self.x_df.src_line.between(src_min_line, src_max_line, inclusive="both"))
            & (self.x_df.src_point.between(src_min_point, src_max_point, inclusive="both"))
        ]

        x_reduced_count = 0
        x_sub_dict = x_sub_df.to_dict(orient="records")
        x_reduced_rows = []
        previous_src_id = ""

        for x_row in x_sub_dict:
            src_line = x_row["src_line"]
            src_point = x_row["src_point"]
            src_id = str(int(src_line)) + str(int(src_point))
            if src_id != previous_src_id:
                selected_src_df = self.src_df[
                    (self.src_df.line == src_line) & (self.src_df.point == src_point)
                ]
                src_easting = float(selected_src_df.easting.iloc[0])
                src_northing = float(selected_src_df.northing.iloc[0])
                previous_src_id = src_id

            rcv_easting = 2 * bin_easting - src_easting
            rcv_northing = 2 * bin_northing - src_northing
            rcv_line, rcv_point = self.bc.calc_rcv_gridpoint(rcv_easting, rcv_northing)
            if (
                (rcv_line - 4 < x_row["rcv_line"] < rcv_line + 4)
                and (x_row["rcv_point_start"] < rcv_point)
                and (x_row["rcv_point_end"] > rcv_point)
            ):
                x_reduced_count += 1
                x_row["rcv_point_start"] = rcv_point - 8
                x_row["rcv_point_end"] = rcv_point + 8
                x_reduced_rows.append(x_row)

            else:
                continue

        if x_reduced_rows:
            self.x_reduced_df = pd.DataFrame(x_reduced_rows)
        print(f"ready, {x_reduced_count=}")

    def create_traces(self) -> None:
        if self.x_reduced_df.empty:
            return

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
        trace_count = 0
        x_dict = self.x_reduced_df.to_dict(orient="records")
        for x_row in x_dict:
            src_line = x_row["src_line"]
            src_point = x_row["src_point"]
            src_index = x_row["src_index"]

            selected_src_df = self.src_df[
                (self.src_df.line == src_line)
                & (self.src_df.point == src_point)
                & (self.src_df.p_index == src_index)
            ]
            src_easting = float(selected_src_df.easting.iloc[0])
            src_northing = float(selected_src_df.northing.iloc[0])
            src_code = selected_src_df.p_code.iloc[0]
            rcv_line = x_row["rcv_line"]
            rcv_point_start = x_row["rcv_point_start"]
            rcv_point_end = x_row["rcv_point_end"]
            rcv_index = x_row["rcv_index"]
            filter_rcv_by_line_df = self.rcv_df[
                (self.rcv_df.line == rcv_line)
                & self.rcv_df.point.between(rcv_point_start, rcv_point_end)
                & (self.rcv_df.p_index == rcv_index)
            ]
            rcv_dict = filter_rcv_by_line_df.to_dict(orient="records")
            for rcv_row in rcv_dict:
                rcv_code = rcv_row["p_code"]
                mid_point_x = (src_easting + rcv_row["easting"]) * 0.5
                mid_point_y = (src_northing + rcv_row["northing"]) * 0.5
                dx = src_easting - rcv_row["easting"]
                dy = src_northing - rcv_row["northing"]
                bin_sp, bin_rp = self.bc.calc_bin_gridpoint(mid_point_x, mid_point_y)
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

        traces_df = pd.DataFrame(traces_dict)
        self.db_general.store_traces_df(traces_df)
        print(f"{trace_count=:,}")
        self.db_general.set_index_traces()
        print(f"complete indexing ...")

def main(argv):
    if len(argv) != 2:
        print("Provide the bins database file as argument!")
        sys.exit()
    db_file = Path(argv[1])

    traces = Traces(db_file)

    t1 = time.time_ns()
    bin_sp = 400
    bin_rp = 732
    traces.x_subset_on_bin(bin_sp, bin_rp)
    traces.create_traces()
    t2 = time.time_ns()
    print(f"trace creation, duration: {(t2 - t1) * 1e-9:.1f} seconds")


if __name__ == "__main__":
    main(sys.argv)
