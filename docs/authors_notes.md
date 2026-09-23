
## Author's notes

*A record of the original run, kept for my own reference. None of this is
needed to use the code.*

### Run logs and the backfilled kernels

`sim_run.py` and `ensemble_run.py` logged every simulation (time, plant, year,
status, duration and output file) to `run_log.csv` and `ensemble_run_log.csv`
in `DROPBOX_DIR`. The logs are not included in the repository. The runtime
figures below come from them.

The first production batch logged 112 runs as `FAIL` with a `PermissionError`.
HYSPLIT had finished each of them correctly; only saving the annual kernel had
failed, because the `kernels/annual/` folder did not exist yet (netCDF4 reports
a missing folder as a permission error). Rather than repeat about 80 CPU-hours of
simulation, the kernels were built from the existing output with
`backfil_kernels.py`, and those plant-years show as `SKIPPED` in the next batch.
The container test in [Validation](#validation) used one of these plant-years
and produced an identical kernel the normal way, so the backfilled kernels match
a normal run.

### Runtime details

| | |
| --- | --- |
| CPU | AMD Ryzen 5 5600X: 6 cores, 12 threads, 4.65 GHz |
| Memory | 32 GB |
| Storage | 1 TB root volume (btrfs) |
| OS | Fedora Linux 44 (Workstation), kernel 7.2.5, glibc 2.43 |

Running ten simulations at once on six physical cores makes each one slower
(about 43 minutes, against about 35 with a whole core each), but completes more
in total: about 13.8 per hour, against about 10.3 when running six at a time.
Two threads were left free to keep the machine usable.

| | Annual runs | Ensemble runs |
| --- | --- | --- |
| Simulations | 1,718 | 735 |
| Mean | 43.1 min | 43.7 min |
| Median | 42.9 min | 43.7 min |
| Interquartile range | 40.5–45.7 min | 42.1–45.5 min |
| Range | 32.2–53.7 min | 34.6–49.6 min |

| | Simulations | Wall clock | CPU time | Throughput |
| --- | --- | --- | --- | --- |
| Annual: 186 plants, FY1973/74–1987/88 | 1,718 | 124.2 h (5.2 days) | 1,235 h | 13.8 runs/h |
| Ensemble: 105 plants × 7 members, FY1981/82 | 735 | 54.0 h (2.2 days) | 535 h | 13.6 runs/h |
| **Total** | **2,453** | **178.2 h (7.4 days)** | **1,770 h (74 days on one core)** | |

### ERA5 download

The download ran from 21:11 on 23 April 2026 to 02:37 on 26 April, 53.4 hours in
all. Four pauses of more than an hour, 12.5 hours in total, returned nothing, so
about 41 hours were spent downloading. With 11 requests running at once, the
average transfer rate was 0.08 MiB/s: the time is spent in the CDS queue, not on
the network.

| | Files | Volume |
| --- | --- | --- |
| Pressure levels (`data/raw/pressures`) | 192 | 9.8 GiB |
| Surface fields (`data/raw/singles`) | 192 | 1.8 GiB |
| **Total** | **384** | **11.6 GiB** |

### Archiving the environment

The Dockerfile will not rebuild in the same way indefinitely: Fedora 44 reaches
end of life on 19 May 2027, after which its packages move to
[archives.fedoraproject.org](https://archives.fedoraproject.org/pub/archive/fedora/linux/),
and download links change. The system packages are therefore not pinned in the
Dockerfile; the verified image is kept instead, with a written record of what
it contains.

The saved image, `cfpp-sim-paper.tar.zst`, is kept in private storage with the
HYSPLIT tarball and the input data (both the image and the tarball contain
HYSPLIT). It was made, and is restored, with:

```bash
docker save cfpp-sim:paper | zstd -T0 -o cfpp-sim-paper.tar.zst
zstd -dc cfpp-sim-paper.tar.zst | docker load
```

`environment/` was written from the image with:

```bash
mkdir -p environment
docker run --rm cfpp-sim:paper rpm -qa | sort > environment/fedora_packages.txt
docker run --rm cfpp-sim:paper conda list -n cfpp_sim --explicit --md5 > environment/cfpp_sim_conda_explicit.txt
docker run --rm cfpp-sim:paper conda list -n cfpp_sim | awk '$NF=="pypi" {print $1"=="$2}' > environment/pip_packages.txt
docker run --rm -w /home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public cfpp-sim:paper \
  sh -c 'find exec bdyfiles -type f | sort | xargs sha256sum' > environment/hysplit_sha256.txt
```

When the image was compared with the original machine (20 September 2026),
every library used in HYSPLIT's calculations matched exactly: glibc 2.43-8, the
GCC runtime libraries 16.2.1-2, NetCDF 4.9.3, NetCDF-Fortran 4.6.2, HDF5 1.14.6
and eccodes 2.48.0-1. Seven support libraries (libcurl, libevent, libselinux,
libtirpc, OpenLDAP, OpenSSL and systemd-libs) were one release behind, because
they come with the base image and are not upgraded by the build; none is used
in the calculations.

If the saved image were lost, the environment can be rebuilt from the
Dockerfile and checked against `environment/`. The conda environment can be
recreated exactly with:

```bash
conda create -n cfpp_sim --file environment/cfpp_sim_conda_explicit.txt
conda run -n cfpp_sim pip install --no-deps -r environment/pip_packages.txt
```

and the HYSPLIT files checked, from inside the HYSPLIT folder, with
`sha256sum -c /path/to/environment/hysplit_sha256.txt`.
