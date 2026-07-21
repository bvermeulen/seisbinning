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
import json
import numpy as np
import sqlite3
from functools import wraps

DEG2RAD = np.pi / 180.0


def read_config(config_file: Path) -> dict:
    with open(config_file, "rt") as jsf:
        config = json.load(jsf)
        config["azimuth"] *= DEG2RAD
    return config


def progress_message_generator(message: str):
    print()
    loop_dash = ["\u2014", "\\", "|", "/"]
    i = 1
    print_interval = 1
    while True:
        print(f"\r{loop_dash[int(i/print_interval) % 4]} {i} {message}", end="")
        i += 1
        yield


class BinCalcs:

    def __init__(self, origin: tuple, bin_src_int: float, bin_rcv_int: float):
        self.x_0 = origin[0]
        self.y_0 = origin[1]
        self.bin_src_int = bin_src_int
        self.bin_rcv_int = bin_rcv_int
        self.cos_azim = np.cos(origin[2])
        self.sin_azim = np.sin(origin[2])
        self.cos_azim_ccw = np.cos(-origin[2])
        self.sin_azim_ccw = np.sin(-origin[2])

    def xy_rotation_clockwise(self, x: float, y: float) -> tuple[float, float]:
        x_trans = x * self.cos_azim + y * self.sin_azim
        y_trans = -x * self.sin_azim + y * self.cos_azim
        return x_trans, y_trans

    def xy_rotation_ccw(self, x: float, y: float) -> tuple[float, float]:
        x_trans = x * self.cos_azim_ccw + y * self.sin_azim_ccw
        y_trans = -x * self.sin_azim_ccw + y * self.cos_azim_ccw
        return x_trans, y_trans

    def calc_bin_coordinate(self, src_distance, rcv_distance) -> tuple[float, float]:
        x, y = self.xy_rotation_clockwise(src_distance, rcv_distance)
        x += self.x_0
        y += self.y_0
        return x, y

    def calc_bin_index(self, x: float, y: float) -> tuple[int, int]:
        x -= self.x_0
        y -= self.y_0
        x, y = self.xy_rotation_ccw(x, y)
        index_sp = round(x / self.bin_src_int)  # replace with round if it does not work
        index_rp = round(y / self.bin_rcv_int)
        return index_sp, index_rp


def db_connect(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = None
        database = args[0].database_file
        try:
            connection = sqlite3.connect(database)
            connection.enable_load_extension(True)
            connection.execute('SELECT load_extension("mod_spatialite")')
            cursor = connection.cursor()
            result = func(*args, cursor, **kwargs)
            connection.commit()

        except sqlite3.Error as error:
            print(f"Error while connect to sqlite {database}: {error}")

        finally:
            if connection:
                cursor.close()
                connection.close()

        return result

    return wrapper


def create_database(database_file):
    connection = None
    try:
        connection = sqlite3.connect(database_file)
        connection.enable_load_extension(True)
        connection.execute('SELECT load_extension("mod_spatialite")')
        connection.execute("SELECT InitSpatialMetaData(1);")
        connection.commit()

    except sqlite3.Error as error:
        print(f"error while connect to sqlite {database_file}: " f"{error}")

    finally:
        if connection:
            connection.close()

    print(f"Database {database_file} created ...")


class DbBins:

    def __init__(
        self,
        database_file: Path,
        table: str,
        epsg: int,
        origin: tuple,
        nb_bin_sp: int,
        nb_bin_rp: int,
        bin_sp_int: float,
        bin_rp_int: float,
    ) -> None:
        self.table = table
        self.epsg = epsg
        self.database_file = database_file
        self.origin = origin
        self.nb_bin_sp = nb_bin_sp
        self.nb_bin_rp = nb_bin_rp
        self.bin_sp_int = bin_sp_int
        self.bin_rp_int = bin_rp_int
        self.calcs = BinCalcs(self.origin, self.bin_sp_int, self.bin_rp_int)

    @db_connect
    def create_config_table(self, cursor):
        sql_string = (
            f"CREATE TABLE IF NOT EXISTS seis_config ("
            f"key TEXT PRIMARY KEY, "
            f"value TEXT NOT NULL);"
        )
        cursor.execute (sql_string)

    @db_connect
    def update_seis_config(self, key, value, cursor):
        sql_string = (
            f"INSERT OR REPLACE INTO seis_config (key, value) "
            f"VALUES (?, ?);"
        )
        cursor.execute(sql_string, (key, value))

    def store_config(self, config: dict):
        self.update_seis_config("file_stem", config["bin_files_stem"])
        self.update_seis_config("azimuth", str(config["azimuth"]))
        self.update_seis_config("easting_orig", str(config["easting"]))
        self.update_seis_config("northing_orig", str(config["northing"]))
        self.update_seis_config("bin_sp_int", str(config["bin_sp_int"]))
        self.update_seis_config("bin_rp_int", str(config["bin_rp_int"]))
        self.update_seis_config("nb_bin_sp", str(config["nb_bin_sp"]))
        self.update_seis_config("nb_bin_rp", str(config["nb_bin_rp"]))
        self.update_seis_config("epsg", str(config["epsg"]))

    @db_connect
    def create_bins_table(self, cursor):
        sql_string = (
            f"CREATE TABLE {self.table} ("
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
            f'SELECT AddGeometryColumn("{self.table}", '
            f'"geom", {self.epsg}, "POINT", "XY");'
        )
        cursor.execute(sql_string)

        print(f"Table {self.table} created ...")

    @db_connect
    def create_bins(self, cursor):
        progress_message = progress_message_generator("Create bins ... ")
        for i in range(self.nb_bin_sp):
            src_distance = i * self.bin_sp_int
            for j in range(self.nb_bin_rp):
                rcv_distance = j * self.bin_rp_int
                x, y = self.calcs.calc_bin_coordinate(src_distance, rcv_distance)
                sql_string = (
                    f"INSERT into {self.table} ("
                    f"bin_sp, bin_rp, easting, northing, bin_count, geom) "
                    f"VALUES ({", ".join(["?"]*5)}, MakePoint(?, ?, ?) "
                    f");"
                )
                cursor.execute(sql_string, (i, j, x, y, None, x, y, self.epsg))
                next(progress_message)


def main():
    config = read_config("./config.json")
    file_stem = config["bin_files_stem"]
    azimuth = config["azimuth"]
    origin = (config["easting"], config["northing"], azimuth)
    bin_rp_int = config["bin_rp_int"]
    bin_sp_int = config["bin_sp_int"]
    nb_bin_sp = config["nb_bin_sp"]
    nb_bin_rp = config["nb_bin_rp"]
    epsg = config["epsg"]

    database_file = Path(file_stem + "_bins.sqlite")
    create_database(database_file)
    db_bins = DbBins(
        database_file,
        "bins",
        epsg,
        origin,
        nb_bin_sp,
        nb_bin_rp,
        bin_sp_int,
        bin_rp_int,
    )
    db_bins.create_config_table()
    db_bins.store_config(config)
    db_bins.create_bins_table()
    db_bins.create_bins()

if __name__ == "__main__":
    main()
