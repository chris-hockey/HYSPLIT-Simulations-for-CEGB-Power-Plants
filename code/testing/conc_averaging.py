import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Polygon
import glob
import os
from collections import defaultdict

working = "/home/chris/hysplit/working"
out_file = "/home/chris/Documents/hysplit_test/data/final/concentration/drax_197401_monthly.shp"


def parse_esri_generate(txt_file, att_file):
    # Parse att file
    att = pd.read_csv(att_file, comment='#', header=None,
                      names=['log_conc', 'name', 'date', 'time', 'llevel', 'hlevel', 'color'])
    log_concs = att['log_conc'].values

    # Parse txt file
    poly_list = []
    current_coords = []
    first_line = True

    with open(txt_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line == 'END':
                if current_coords:
                    poly_list.append(Polygon(current_coords))
                    current_coords = []
                first_line = True
                continue
            parts = [float(x) for x in line.replace(',', ' ').split()]
            if first_line:
                # first line is: id, lon, lat
                current_coords = [(parts[1], parts[2])]
                first_line = False
            else:
                current_coords.append((parts[0], parts[1]))

    return poly_list, log_concs


# Get all days
txt_files = sorted(glob.glob(os.path.join(working, "polygons_*_html.txt")))
att_files = sorted(glob.glob(os.path.join(working, "polygons_*_html.att")))

print(f"Found {len(txt_files)} days")

conc_sum = defaultdict(float)
conc_count = defaultdict(int)

for txt, att in zip(txt_files, att_files):
    polys_day, log_concs_day = parse_esri_generate(txt, att)
    for poly, lc in zip(polys_day, log_concs_day):
        key = (round(poly.centroid.x, 4), round(poly.centroid.y, 4))
        conc_sum[key] += 10**lc
        conc_count[key] += 1

records = []
for key, total in conc_sum.items():
    lon, lat = key
    poly = Polygon([
        (lon - 0.025, lat - 0.025),
        (lon + 0.025, lat - 0.025),
        (lon + 0.025, lat + 0.025),
        (lon - 0.025, lat + 0.025),
        (lon - 0.025, lat - 0.025)
    ])
    records.append({
        'geometry': poly,
        'conc_total': total,
        'conc_mean': total / conc_count[key],
        'lon': lon,
        'lat': lat
    })

gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
gdf.to_file(out_file)
print(f"Saved {len(gdf)} grid cells to {out_file}")
