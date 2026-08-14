from pathlib import Path
import pandas as pd

class SpsParse:
    def __init__(self, config):
        self.config = config
        self._source_indexes = None

    @property
    def source_indexes(self):
        return(self._source_indexes)

    def read_sps_rcv(self) -> pd.DataFrame:
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

    def read_sps_src(self) -> pd.DataFrame:
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
        self._src_indexes = set()
        for line in lines:
            if line[0] != "S":
                continue

            p_index = int(line[21:24])
            if (p_code := line[24:26].strip()) == "KL":
                continue

            src_dict["type"].append(line[0:1])
            src_dict["line"].append(float(line[1:11]))
            src_dict["point"].append(float(line[11:21]))
            src_dict["p_index"].append(p_index)
            src_dict["p_code"].append(p_code)
            src_dict["easting"].append(float(line[45:55]))
            src_dict["northing"].append(float(line[55:65]))
            src_dict["elevation"].append(
                (float(line[66:75]) if line[65:74].replace(" ", "") else 0.0)
            )
            self._src_indexes.add(p_index)

        src_df = pd.DataFrame(src_dict)
        return src_df

    def read_sps_x(self) -> pd.DataFrame:
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
