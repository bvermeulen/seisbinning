"""
create bins application
conventions:
azimuth zero -
    source increase with x axis
    receivers increase with y axis

azimuth 90 -
    source decrease with y axis
    receivers increase with x axis
    use negative source_bin_interval to have source to increase with y axis
"""

from pathlib import Path
from dbase_module import progress_message_generator, DbConnect, CreateDB, DbGeneral
import json
import numpy as np

DEG2RAD = np.pi / 180.0




class BinCalcs:

    def __init__(self, config: dict):
        bin_origin = (
            config["bin_easting_origin"],
            config["bin_northing_origin"],
            config["azimuth"] * DEG2RAD,
        )
        self.bin_src_int = config["bin_sp_int"]
        self.bin_rcv_int = config["bin_rp_int"]
        self.bin_x_o = bin_origin[0]
        self.bin_y_o = bin_origin[1]
        self.cos_azim = np.cos(bin_origin[2])
        self.sin_azim = np.sin(bin_origin[2])
        self.cos_azim_ccw = np.cos(-bin_origin[2])
        self.sin_azim_ccw = np.sin(-bin_origin[2])

        self.rcv_x_o = config["rcv_easting_origin"]
        self.rcv_y_o = config["rcv_northing_origin"]
        self.rcv_line_o = config["rcv_line_origin"]
        self.rcv_point_o = config["rcv_point_origin"]
        self.rl_int = config["rl_int"]
        self.rp_int = config["rp_int"]
        self.src_x_o = config["src_easting_origin"]
        self.src_y_o = config["src_northing_origin"]
        self.src_line_o = config["src_line_origin"]
        self.src_point_o = config["src_point_origin"]
        self.sl_int = config["sl_int"]
        self.sp_int = config["sp_int"]

    def xy_rotation_clockwise(self, x: float, y: float) -> tuple[float, float]:
        x_trans = x * self.cos_azim + y * self.sin_azim
        y_trans = -x * self.sin_azim + y * self.cos_azim
        return x_trans, y_trans

    def xy_rotation_ccw(self, x: float, y: float) -> tuple[float, float]:
        x_trans = x * self.cos_azim_ccw + y * self.sin_azim_ccw
        y_trans = -x * self.sin_azim_ccw + y * self.cos_azim_ccw
        return x_trans, y_trans

    def calc_bin_on_dist(
        self, src_distance: float, rcv_distance: float
    ) -> tuple[float, float]:
        x, y = self.xy_rotation_clockwise(src_distance, rcv_distance)
        x += self.bin_x_o
        y += self.bin_y_o
        return x, y

    def calc_bin_xy(self, bin_sp: int, bin_rp: int) -> tuple[float, float]:
        src_distance = bin_sp * self.bin_src_int
        rcv_distance = bin_rp * self.bin_rcv_int
        x, y = self.calc_bin_on_dist(src_distance, rcv_distance)
        return x, y

    def calc_bin_gridpoint(self, x: float, y: float) -> tuple[int, int]:
        x -= self.bin_x_o
        y -= self.bin_y_o
        x, y = self.xy_rotation_ccw(x, y)
        index_sp = round(x / self.bin_src_int)  # replace with round if it does not work
        index_rp = round(y / self.bin_rcv_int)
        return index_sp, index_rp

    def calc_rcv_xy(self, line: int, point: int) -> tuple[float, float]:
        # receiver lines are oriented along the north (y) axis
        x = np.sign(self.sp_int) * (line - self.rcv_line_o) * self.rp_int
        y = (point - self.rcv_point_o) * self.rp_int
        x_trans, y_trans = self.xy_rotation_clockwise(x, y)
        easting = x_trans + self.rcv_x_o
        northing = y_trans + self.rcv_y_o
        return easting, northing

    def calc_src_xy(self, line: int, point: int) -> tuple[float, float]:
        # source lines are oriented along the east (x) axis
        x = np.sign(self.sp_int) * (point - self.src_point_o) * self.rp_int
        y = (line - self.src_line_o) * self.rp_int
        x_trans, y_trans = self.xy_rotation_clockwise(x, y)
        easting = x_trans + self.src_x_o
        northing = y_trans + self.src_y_o
        return easting, northing

    def calc_rcv_gridpoint(self, easting: float, northing: float) -> tuple[int, int]:
        x = northing - self.rcv_y_o
        y = np.sign(self.sp_int) * (easting - self.rcv_x_o)
        x_trans, y_trans = self.xy_rotation_ccw(x, y)
        line = round(y_trans / self.rp_int + self.rcv_line_o)
        point = round(x_trans / self.rp_int + self.rcv_point_o)
        return line, point

    def calc_src_gridpoint(self, easting: float, northing: float) -> tuple[int, int]:
        x = northing - self.src_y_o
        y = np.sign(self.sp_int) * (easting - self.src_x_o)
        x_trans, y_trans = self.xy_rotation_ccw(x, y)
        line = round(x_trans / self.rp_int + self.src_line_o)
        point = round(y_trans / self.rp_int + self.src_point_o)
        return line, point

    def calc_bin_sp_extent(
        self, easting: float, northing: float, offset: float
    ) -> tuple[int, int, int, int]:
        x_trans, y_trans = self.xy_rotation_clockwise(offset, offset)
        src_x_min = easting - x_trans
        src_x_max = easting + x_trans
        src_y_min = northing - y_trans
        src_y_max = northing + y_trans
        line_1, point_1 = self.calc_src_gridpoint(src_x_min, src_y_min)
        line_2, point_2 = self.calc_src_gridpoint(src_x_max, src_y_max)
        return (
            min(line_1, line_2),
            max(line_1, line_2),
            min(point_1, point_2),
            max(point_1, point_2),
        )


class DbBins:

    def __init__(self, config, bins_table) -> None:
        file_stem = config["file_stem"]
        self.database_file = Path(file_stem + ".sqlite")
        self.bins_table = bins_table
        self.epsg = config["epsg"]
        self.bin_origin = (
            config["bin_easting_origin"],
            config["bin_northing_origin"],
            config["azimuth"] * DEG2RAD,
        )
        self.nb_bin_sp = config["nb_bin_sp"]
        self.nb_bin_rp = config["nb_bin_rp"]
        self.bin_sp_int = config["bin_sp_int"]
        self.bin_rp_int = config["bin_rp_int"]
        self.calcs = BinCalcs(config)

    @DbConnect
    def create_bins_table(self, cursor):
        DbGeneral(self.database_file).delete_table(self.bins_table)
        sql_string = (
            f"CREATE TABLE {self.bins_table} ("
            f"id INTEGER PRIMARY KEY, "
            f"bin_sp INTEGER, "
            f"bin_rp INTEGER, "
            f"easting DOUBLE PRECISION, "
            f"northing DOUBLE PRECISION, "
            f"bin_count INT "
            f");"
        )
        cursor.executescript(sql_string)

        # once table is created you can add the geomety column
        sql_string = (
            f'SELECT AddGeometryColumn("{self.bins_table}", '
            f'"geom", {self.epsg}, "POINT", "XY");'
        )
        cursor.execute(sql_string)

        print(f"Table {self.bins_table} created ...")

    @DbConnect
    def create_bins(self, cursor):
        progress_message = progress_message_generator("Create bins ... ")
        for i in range(self.nb_bin_sp):
            src_distance = i * self.bin_sp_int
            for j in range(self.nb_bin_rp):
                rcv_distance = j * self.bin_rp_int
                x, y = self.calcs.calc_bin_on_dist(src_distance, rcv_distance)
                sql_string = (
                    f"INSERT into {self.bins_table} ("
                    f"bin_sp, bin_rp, easting, northing, bin_count, geom) "
                    f"VALUES ({", ".join(["?"]*5)}, MakePoint(?, ?, ?) "
                    f");"
                )
                cursor.execute(sql_string, (i, j, x, y, None, x, y, self.epsg))
                next(progress_message)
        print()

def main():
    db = CreateDB("./config_khlieseia.json")
    config = db.config
    bins_table = "bins"
    db_bins = DbBins(config, bins_table)
    db_bins.create_bins_table()
    db_bins.create_bins()
    bc = BinCalcs(config)
    line = 5043
    point = 1147
    easting, northing = bc.calc_src_xy(line, point)
    print(f"{line=}, {point=}, {easting=}, {northing=}")
    line1, point1 = bc.calc_src_gridpoint(easting, northing)
    print(f"{easting=}, {northing=}, {line1=}, {point1=}")
    pass

    min_line, max_line, min_point, max_point = bc.calc_bin_sp_extent(
        easting, northing, 1000
    )
    print(f"{min_line=}, {max_line=}, {min_point=}, {max_point=}")
    bin_sp = 779
    bin_rp = 893
    easting, northing = bc.calc_bin_xy(bin_sp, bin_rp)
    print(f"{easting=}, {northing=}, {bin_sp=}, {bin_rp=}")
    bin_sp, bin_rp = bc.calc_bin_gridpoint(easting, northing)
    print(f"{easting=}, {northing=}, {bin_sp=}, {bin_rp=}")


if __name__ == "__main__":
    main()
