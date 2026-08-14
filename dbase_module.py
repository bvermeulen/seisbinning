import json
from pathlib import Path
import sqlite3
import pandas as pd
from sqlalchemy import create_engine
from sps_parse import SpsParse


def progress_message_generator(message: str):
    print()
    loop_dash = ["\u2014", "\\", "|", "/"]
    i = 1
    print_interval = 1
    while True:
        print(f"\r{loop_dash[int(i/print_interval) % 4]} {i} {message}", end="")
        i += 1
        yield


db_tables = {
    "seis_config": "seis_config",
    "sps_rcv": "sps_rcv",
    "sps_src": "sps_src",
    "sps_x": "sps_x",
    "traces": "traces",
}


class DbConnect:
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, _):
        if instance is None:
            return self

        def inner(*args, **kwargs):
            result = None
            try:
                connection = sqlite3.connect(instance.database_file)
                connection.enable_load_extension(True)
                connection.execute('SELECT load_extension("mod_spatialite")')
                cursor = connection.cursor()
                result = self.func(instance, *args, cursor, **kwargs)
                connection.commit()

            except sqlite3.Error as error:
                print(
                    f"Error while connect to sqlite {instance.database_file}: {error}"
                )

            finally:
                if connection:
                    cursor.close()
                    connection.close()

            return result

        return inner


class CreateDB:
    def __init__(self, config_file):
        self.config_table = db_tables["seis_config"]
        self.rcv_table = db_tables["sps_rcv"]
        self.src_table = db_tables["sps_src"]
        self.x_table = db_tables["sps_x"]
        self._config = self.read_config(config_file)
        file_stem = self._config["file_stem"]

        #self.database_file is necessary for @DbConnect class
        self.database_file = Path(file_stem + ".sqlite")
        self.create_database(self.database_file)
        self.engine = create_engine("".join(["sqlite:///", str(self.database_file)]))
        self.store_config()
        self.store_sps()

    def create_database(self, database_file):
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

    @staticmethod
    def read_config(config_file: Path) -> dict:
        with open(config_file, "rt") as jsf:
            config = json.load(jsf)
        return config

    @property
    def config(self):
        return self._config

    @DbConnect
    def create_config_table(self, cursor):
        self.delete_table(self.config_table)
        sql_string = (
            f"CREATE TABLE {self.config_table} ("
            f"key TEXT PRIMARY KEY, "
            f"value TEXT NOT NULL);"
        )
        cursor.execute(sql_string)

    @DbConnect
    def delete_table(self, table, cursor):
        sql_string = f"DROP TABLE IF EXISTS {table};"
        cursor.executescript(sql_string)

    @DbConnect
    def update_seis_config(self, key, value, cursor):
        sql_string = (
            f"INSERT OR REPLACE INTO {self.config_table} (key, value) "
            f"VALUES (?, ?);"
        )
        cursor.execute(sql_string, (key, value))

    def store_config(self):
        config = self.config
        self.delete_table(self.config_table)
        self.create_config_table()

        self.update_seis_config("file_stem", config["file_stem"])
        self.update_seis_config("azimuth", str(config["azimuth"]))
        self.update_seis_config("bin_easting_origin", str(config["bin_easting_origin"]))
        self.update_seis_config(
            "bin_northing_origin", str(config["bin_northing_origin"])
        )
        self.update_seis_config("bin_sp_int", str(config["bin_sp_int"]))
        self.update_seis_config("bin_rp_int", str(config["bin_rp_int"]))
        self.update_seis_config("nb_bin_sp", str(config["nb_bin_sp"]))
        self.update_seis_config("nb_bin_rp", str(config["nb_bin_rp"]))
        self.update_seis_config("rcv_easting_origin", str(config["rcv_easting_origin"]))
        self.update_seis_config(
            "rcv_northing_origin", str(config["rcv_northing_origin"])
        )
        self.update_seis_config("rcv_line_origin", str(config["rcv_line_origin"]))
        self.update_seis_config("rcv_point_origin", str(config["rcv_point_origin"]))
        self.update_seis_config("rl_int", str(config["rl_int"]))
        self.update_seis_config("rp_int", str(config["rp_int"]))
        self.update_seis_config("src_easting_origin", str(config["src_easting_origin"]))
        self.update_seis_config(
            "src_northing_origin", str(config["src_northing_origin"])
        )
        self.update_seis_config("src_line_origin", str(config["src_line_origin"]))
        self.update_seis_config("src_point_origin", str(config["src_point_origin"]))
        self.update_seis_config("sl_int", str(config["sl_int"]))
        self.update_seis_config("sp_int", str(config["sp_int"]))
        self.update_seis_config("epsg", str(config["epsg"]))
        self.update_seis_config("offset", "0")
        self.update_seis_config("src_indexes", "0")

    def store_sps_df(self, df, type):
        match type.lower():
            case "rcv":
                table = self.rcv_table
            case "src":
                table = self.src_table
            case "x":
                table = self.x_table
            case _:
                assert False, "wrong type of SPS table"

        self.delete_table(table)
        df.to_sql(name=table, con=self.engine, if_exists="replace", index=False)

    def store_sps(self):
        sps = SpsParse(self.config)
        self.store_sps_df(sps.read_sps_rcv(), "rcv")
        self.store_sps_df(sps.read_sps_src(), "src")
        self.store_sps_df(sps.read_sps_x(), "x")
        src_indexes = sps._src_indexes
        self.update_seis_config("src_indexes", ",".join([str(v) for v in src_indexes]))


class DbGeneral:
    def __init__(self, database_file):
        self.database_file = database_file
        self.config_table = db_tables["seis_config"]
        self.rcv_table = db_tables["sps_rcv"]
        self.src_table = db_tables["sps_src"]
        self.x_table = db_tables["sps_x"]
        self.traces_table = db_tables["traces"]
        self._engine = create_engine("".join(["sqlite:///", str(database_file)]))

    @property
    def engine(self):
        return self._engine

    @DbConnect
    def get_config_from_db(self, cursor):
        sql_string = f"select value from {self.config_table} WHERE key = ?"
        config = {}
        config["file_stem"] = cursor.execute(sql_string, ("file_stem",)).fetchone()[0]
        config["azimuth"] = float(
            cursor.execute(sql_string, ("azimuth",)).fetchone()[0]
        )
        config["bin_easting_origin"] = float(
            cursor.execute(sql_string, ("bin_easting_origin",)).fetchone()[0]
        )
        config["bin_northing_origin"] = float(
            cursor.execute(sql_string, ("bin_northing_origin",)).fetchone()[0]
        )
        config["bin_sp_int"] = float(
            cursor.execute(sql_string, ("bin_sp_int",)).fetchone()[0]
        )
        config["bin_rp_int"] = float(
            cursor.execute(sql_string, ("bin_rp_int",)).fetchone()[0]
        )
        config["nb_bin_sp"] = int(
            float(cursor.execute(sql_string, ("nb_bin_sp",)).fetchone()[0])
        )
        config["nb_bin_rp"] = int(
            float(cursor.execute(sql_string, ("nb_bin_rp",)).fetchone()[0])
        )
        config["rcv_easting_origin"] = float(
            float(cursor.execute(sql_string, ("rcv_easting_origin",)).fetchone()[0])
        )
        config["rcv_northing_origin"] = float(
            float(cursor.execute(sql_string, ("rcv_northing_origin",)).fetchone()[0])
        )
        config["rcv_line_origin"] = int(
            float(cursor.execute(sql_string, ("rcv_line_origin",)).fetchone()[0])
        )
        config["rcv_point_origin"] = int(
            float(cursor.execute(sql_string, ("rcv_point_origin",)).fetchone()[0])
        )
        config["rl_int"] = float(
            float(cursor.execute(sql_string, ("rl_int",)).fetchone()[0])
        )
        config["rp_int"] = float(
            float(cursor.execute(sql_string, ("rp_int",)).fetchone()[0])
        )
        config["src_easting_origin"] = float(
            float(cursor.execute(sql_string, ("src_easting_origin",)).fetchone()[0])
        )
        config["src_northing_origin"] = float(
            float(cursor.execute(sql_string, ("src_northing_origin",)).fetchone()[0])
        )
        config["src_line_origin"] = int(
            float(cursor.execute(sql_string, ("src_line_origin",)).fetchone()[0])
        )
        config["src_point_origin"] = int(
            float(cursor.execute(sql_string, ("src_point_origin",)).fetchone()[0])
        )
        config["sl_int"] = float(
            float(cursor.execute(sql_string, ("sl_int",)).fetchone()[0])
        )
        config["sp_int"] = float(
            float(cursor.execute(sql_string, ("sp_int",)).fetchone()[0])
        )
        config["epsg"] = int(float(cursor.execute(sql_string, ("epsg",)).fetchone()[0]))
        config["offset"] = float(cursor.execute(sql_string, ("offset",)).fetchone()[0])
        config["src_indexes"] = [
            int(v)
            for v in cursor.execute(sql_string, ("src_indexes",))
            .fetchone()[0]
            .split(",")
        ]
        return config

    @DbConnect
    def update_seis_config(self, key, value, cursor):
        sql_string = (
            f"INSERT OR REPLACE INTO {self.config_table} (key, value) "
            f"VALUES (?, ?);"
        )
        cursor.execute(sql_string, (key, value))

    @DbConnect
    def delete_table(self, table, cursor):
        sql_string = f"DROP TABLE IF EXISTS {table};"
        cursor.executescript(sql_string)

    @DbConnect
    def create_sps_rcv_table(self, cursor):
        self.delete_table(self.rcv_table)
        sql_string = (
            f"CREATE TABLE {self.rcv_table} ("
            f"id INTEGER PRIMARY KEY, "
            f"type VAR(1), "
            f"line REAL, "
            f"point REAL, "
            f"p_index INTEGER, "
            f"p_code VAR(2), "
            f"easting DOUBLE PRECISION, "
            f"northing DOUBLE PRECISION, "
            f"elevation REAL"
            f");"
        )
        cursor.executescript(sql_string)

    @DbConnect
    def create_sps_src_table(self, cursor):
        self.delete_table(self.src_table)
        sql_string = (
            f"CREATE TABLE {self.src_table} ("
            f"id INTEGER PRIMARY KEY, "
            f"type VAR(1), "
            f"line REAL, "
            f"point REAL, "
            f"p_index INTEGER, "
            f"p_code VAR(2), "
            f"easting DOUBLE PRECISION, "
            f"northing DOUBLE PRECISION, "
            f"elevation REAL"
            f");"
        )
        cursor.executescript(sql_string)

    @DbConnect
    def create_sps_x_table(self, cursor):
        self.delete_table(self.x_table)
        sql_string = (
            f"CREATE TABLE {self.x_table} ("
            f"id INTEGER PRIMARY KEY, "
            f"type VAR(1), "
            f"src_line REAL, "
            f"src_point REAL, "
            f"src_index INTEGER, "
            f"chan_start INTEGER, "
            f"chan_end INTEGER, "
            f"rcv_line REAL, "
            f"rcv_point_start INTEGER, "
            f"rcv_point_end INTEGER, "
            f"rcv_index INTEGER, "
            f"tb var(50)"
            f");"
        )
        cursor.executescript(sql_string)

    @DbConnect
    def create_traces_table(self, cursor):
        self.delete_table(self.traces_table)
        sql_string = (
            f"CREATE TABLE {self.traces_table} ("
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
        cursor.executescript(sql_string)

    def read_sps_df(self, type: str):
        match type.lower():
            case "rcv":
                table = self.rcv_table
            case "src":
                table = self.src_table
            case "x":
                table = self.x_table
            case _:
                assert False, "wrong type of SPS table"

        return pd.read_sql_table(table, con=self._engine)

    def store_traces_df(self, df):
        df.to_sql(
            name=self.traces_table, con=self.engine, if_exists="replace", index=False
        )

    @DbConnect
    def set_index_traces(self, cursor):
        sql_string = "DROP INDEX IF EXISTS bin_idx"
        cursor.execute(sql_string)

        sql_string = f"CREATE INDEX bin_idx ON {self.traces_table} (bin_sp, bin_rp);"
        cursor.execute(sql_string)
