from bins import read_config, calc_bin_coordinate, calc_bin_index
import numpy as np

def create_bins(origin, bin_src_int, bin_rcv_int, src_bins, rcv_bins):
    bins = np.empty((src_bins, rcv_bins), dtype=object)
    for i in range(src_bins):
        src_distance = i * bin_src_int
        for j in range(rcv_bins):
            rcv_distance = j * bin_rcv_int
            x, y = calc_bin_coordinate(origin, src_distance, rcv_distance)
            bins[i, j] = (x, y)           
    return bins

def test():
    config = read_config()
    azimuth = config["azimuth"]
    origin = (
        config["easting"], 
        config["northing"],
        azimuth
    )
    bin_rcv_int = config["bin_rp_int"]
    bin_src_int = config["bin_sp_int"]
    rcv_bins = config["nb_bin_rp"]
    src_bins = config["nb_bin_sp"]
    bins = create_bins(origin, bin_src_int, bin_rcv_int, src_bins, rcv_bins)
    for bin in bins:
        print(bin)

    # test point at zero azimuth
    x = 37.5    # 701692.75
    y = 50.0 # 3450642.50
    # x, y = xy_rotation_clockwise(x - origin[0], y - origin[1], origin[2])
    # x += origin[0]
    # y += origin[1]
    i, j = calc_bin_index(x, y, origin, bin_src_int, bin_rcv_int)
    print(f"(x, y) = ({x:.1f}, {y:.1f}), bins[{i}, {j}]")
    # print(
    #     f"(x, y) = ({x:.1f}, {y:.1f}), bins[{i}, {j}] = {bins[i,j]}, {x - bins[i,j][0]:.4f}, {y - bins[i,j][1]:.4f}"
    # )
    print(f"{bins[2,3]=}")


if __name__ == "__main__":
    test()
