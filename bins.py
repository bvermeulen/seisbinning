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

def read_config() -> dict:
    with open("./config.json", "rt") as jsf:
        config = json.load(jsf)
        config["azimuth"] *= DEG2RAD 
    return config


def progress_message_generator(message):
    print()
    loop_dash = ["\u2014", "\\", "|", "/"]
    i = 1
    print_interval = 1
    while True:
        print(f"\r{loop_dash[int(i/print_interval) % 4]} {i} {message}", end="")
        i += 1
        yield


def xy_rotation_clockwise(x: float, y: float, azimuth: float) -> tuple[float, float]:
    cos_azim = np.cos(azimuth)
    sin_azim = np.sin(azimuth)
    x_trans = x * cos_azim + y * sin_azim
    y_trans = -x * sin_azim + y * cos_azim
    return x_trans, y_trans


def calc_bin_coordinate(
    origin: tuple, src_distance, rcv_distance
) -> tuple[float, float]:
    x, y = xy_rotation_clockwise(src_distance, rcv_distance, origin[2])
    x += origin[0]
    y += origin[1]
    return x, y


def calc_bin_index(
    x: float,
    y: float,
    origin: tuple[float, float, float],
    bin_src_int: float,
    bin_rcv_int: float,
) -> tuple[int, int]:
    x -= origin[0]
    y -= origin[1]
    x, y = xy_rotation_clockwise(x, y, -origin[2])
    index_sp = int(x / bin_src_int)  # replace with round if it does not work
    index_rp = int(y / bin_rcv_int)
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
                x, y = calc_bin_coordinate(self.origin, src_distance, rcv_distance)
                sql_string = (
                    f"INSERT into {self.table} ("
                    f"bin_sp, bin_rp, easting, northing, bin_count, geom) "
                    f"VALUES ({", ".join(["?"]*5)}, MakePoint(?, ?, ?) "
                    f");"
                )
                cursor.execute(sql_string, (i, j, x, y, None, x, y, self.epsg))
                next(progress_message)


def main():
    config = read_config()
    file_stem = config["bin_files_stem"]
    azimuth = config["azimuth"]
    origin = (config["easting"], config["northing"], azimuth)
    bin_rp_int = config["bin_rp_int"]
    bin_sp_int = config["bin_sp_int"]
    nb_bin_sp = config["nb_bin_sp"]
    nb_bin_rp = config["nb_bin_rp"]

    database_file = Path(file_stem + "_bins.sqlite")
    epsg = 32638
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
    db_bins.create_bins_table()
    db_bins.create_bins()


if __name__ == "__main__":
    main()
