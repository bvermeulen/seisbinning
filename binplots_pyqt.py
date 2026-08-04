"""PyQt shell for bin_attributes
author: Bruno Vermeulen
email: bvermeulen@hotmail.com
©2026 howdimain
admin@howdiweb.nl
"""

import sys
import datetime
from functools import partial
import warnings
from pathlib import Path
import numpy as np
from bins import DbTools
from bin_attributes import BinAttributes, PlotOffset, PlotSpider, PlotRose
from PyQt6 import uic, QtWidgets
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

matplotlib.use("QtAgg")
warnings.filterwarnings("ignore", category=UserWarning)


class MplCanvas(FigureCanvas):
    def __init__(self, fig):
        super().__init__(fig)

class PyqtViewControl(QtWidgets.QMainWindow):
    """PyQt view and control"""

    def __init__(self, arguments, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi(Path(__file__).parent / "binning_plots.ui", self)
        if len(arguments) != 2:
            print("Provide the db file name as the first argument ...")
        self.bins_file_stem = Path(arguments[1]).parent / Path(arguments[1]).stem
        self.config = DbTools(arguments[1]).get_config_from_db()
        self.save_folder_description = "Save to: "
        self.ActionQuit.triggered.connect(self.quit)
        self.ActionDefaultDatabase.triggered.connect(
            partial(self.select_database, default=True)
        )
        self.ActionSelectDatabase.triggered.connect(
            partial(self.select_database, default=False)
        )
        self.ActionSaveFolder.triggered.connect(self.select_save_folder)
        self.ActionSave.triggered.connect(partial(self.save_plots))
        self.LineEdit_01.returnPressed.connect(self.select_bin)
        self.LineEdit_06.returnPressed.connect(self.select_bin)
        self.LineEdit_07.returnPressed.connect(self.select_bin)

        self.plot_dict = {}
        self.clear_vals()
        for _, value in self.plot_dict.items():
            value["rb"].clicked.connect(partial(self.show_plot, value["index"] - 1))
        self.save_folder = self.bins_file_stem.parent / "bin_plots"
        self.RB_Type_01.setChecked(True)
        self.DbLabel.setText(self.bins_file_stem.name)
        self.SaveFolderLabel.setText(
            "".join([self.save_folder_description, str(self.save_folder)])
        )

    def clear_vals(self):
        if self.plot_dict:
            self.update_canvas_data({})

        self.plot_dict = {
            "Offset": {
                "index": 1,
                "canvas": None,
                "rb": self.RB_Type_01,
                "layout": self.FormLayout_01,
                "file_name": "bin_offset",
                "fig": None,
            },
            "Spider": {
                "index": 2,
                "canvas": None,
                "rb": self.RB_Type_02,
                "layout": self.FormLayout_02,
                "file_name": "bin_spider",
                "fig": None,
            },
            "Rose": {
                "index": 3,
                "canvas": None,
                "rb": self.RB_Type_03,
                "layout": self.FormLayout_03,
                "file_name": "bin_rose",
                "fig": None,
            },
        }
        self.LineEdit_01.setText("")
        self.LineEdit_02.setText("")
        self.LineEdit_03.setText("")
        self.LineEdit_04.setText("")
        self.LineEdit_05.setText("")
        self.LineEdit_06.setText(
            f"{", ".join(str(i) for i in self.config["src_indexes"])}"
        )
        self.LineEdit_07.setText(f"{int(self.config["offset"])}")
        self.figure_dict = {}
        self.center_bin_name = ""
        self.bins_df = np.array([])
        self.offset = None
        self.src_indexes = []

    def select_bin(self):
        bin = self.LineEdit_01.text()
        for delimeter in ["/", ",", ";"]:
            bin = bin.replace(delimeter, " ")
        try:
            bin_src, bin_rcv = [int(v) for v in bin.split()]
            if bin_src < 1 or bin_rcv < 1:
                raise ValueError("bin must be positive")

        except ValueError:
            return

        indexes = self.LineEdit_06.text()
        for delimeter in ["/", ",", ";"]:
            self.src_indexes = indexes.replace(delimeter, " ")
        try:
            self.src_indexes = [int(v) for v in indexes.split()]
            if not self.src_indexes or not all(v > 0 for v in self.src_indexes):
                raise ValueError("all indexes must be positive")

        except ValueError:
            return

        offset = self.LineEdit_07.text()
        try:
            self.offset = float(offset)
            if not (self.offset > 0):
                raise ValueError("max offset must be positive")

        except ValueError:
            return

        self.center_bin_name = f"{bin_src}_{bin_rcv}"
        self.db_file = self.bins_file_stem.with_suffix(".sqlite")
        ba = BinAttributes(self.db_file, (bin_src, bin_rcv), self.offset, self.src_indexes)
        self.bins_df = ba.get_surrounding_bins()
        self.update_attribute_figs()
        del ba

    def update_attribute_figs(self):
        if self.bins_df.size == 0:
            return

        width = self.PlotFrame.width() / self.PlotFrame.logicalDpiX()
        height = self.PlotFrame.height() / self.PlotFrame.logicalDpiY()
        figsize = (width, height)
        plot_offset = PlotOffset(self.bins_df, figsize)
        plot_spider = PlotSpider(self.bins_df, self.offset, figsize)
        plot_rose = PlotRose(self.bins_df, self.offset, figsize)
        bin_line, bin_point, easting, northing, traces = plot_offset.calc_bin_values(0, 0)
        self.LineEdit_02.setText(f"{easting:.0f}")
        self.LineEdit_03.setText(f"{northing:.0f}")
        self.LineEdit_04.setText(f"{bin_line}/ {bin_point}")
        self.LineEdit_05.setText(f"{traces}")
        self.LineEdit_06.setText(f"{", ".join(str(i) for i in self.src_indexes)}")
        self.LineEdit_07.setText(f"{int(self.offset)}")
        self.figure_dict["Offset"] = plot_offset.diagram()
        self.figure_dict["Spider"] = plot_spider.diagram()
        self.figure_dict["Rose"] = plot_rose.diagram()
        self.update_canvas_data(self.figure_dict)
        # make sure there is destructor (__del__) to apply plt.close('all') to remove all figures
        del plot_offset
        del plot_spider
        del plot_rose

    def update_canvas_data(self, figure_dict):

        for key, value in self.plot_dict.items():
            value["fig"] = figure_dict.get(key)
            if value["canvas"]:
                value["canvas"].hide()
                value["layout"].removeWidget(value["canvas"])
                value["canvas"] = None

            if value["fig"]:
                value["canvas"] = MplCanvas(value["fig"])
                value["layout"].addWidget(value["canvas"])

    def show_plot(self, plot_index: int):
        self.StackedPlots.setCurrentIndex(plot_index)

    def select_database(self, default=True):
        if default:
            self.bins_file_stem = Path(self.config["file_stem"])

        else:
            bfn = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Open file",
                str(self.bins_file_stem),
                "SQLite files (*.sqlite3 *.sqlite);; All (*.*)",
            )[0]
            self.bins_file_stem = Path(bfn).parent / Path(bfn).stem

        self.DbLabel.setText(self.bins_file_stem.stem)
        self.config = DbTools(
            self.bins_file_stem.with_suffix(".sqlite")
        ).get_config_from_db()
        self.clear_vals()

    def select_save_folder(self):
        save_folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select a save folder",
            directory=Path(self.bins_file_stem).parent.as_posix(),
        )
        if save_folder:
            self.save_folder = Path(save_folder)

        self.SaveFolderLabel.setText(
            "".join([self.save_folder_description, str(self.save_folder)])
        )

    def save_plots(self):
        base_file_name = "".join([datetime.datetime.now().strftime("%y%m%d"), "_"])
        for _, value in self.plot_dict.items():
            if not (fig := value["fig"]):
                continue

            file_name = self.save_folder / "".join(
                [
                    base_file_name,
                    value.get("file_name"),
                    "_",
                    self.center_bin_name,
                    ".png",
                ]
            )
            fig.savefig(file_name)

    def resizeEvent(self, event):
        self.update_attribute_figs()
        super().resizeEvent(event)

    def quit(self):
        sys.exit()


def start_app():
    app = QtWidgets.QApplication(sys.argv)
    view_control = PyqtViewControl(app.arguments())
    view_control.show()
    app.exec()


if __name__ == "__main__":
    start_app()
