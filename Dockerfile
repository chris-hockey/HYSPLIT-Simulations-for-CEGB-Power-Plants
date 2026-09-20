# Snapshot of the machine the CEGB power plant HYSPLIT simulations ran on:
# Fedora 44, the cfpp_sim environment, HYSPLIT v5.4.2, and the original
# directory layout, so the code runs unmodified. See README.md, "Option B".

FROM --platform=linux/amd64 fedora:44@sha256:43b29f65a41eb9c35e1cd5323e3bdf3b655c2357a9f4f1ff2f9c2798e5045d80

RUN dnf -y install \
      bzip2-libs cyrus-sasl-lib eccodes eccodes-data \
      glibc hdf-libs hdf5 jasper-libs \
      keyutils-libs krb5-libs libaec libbrotli \
      libcbor libcom_err libcurl libevent \
      libfido2 libgcc libgfortran libgomp \
      libidn2 libjpeg-turbo libnghttp2 libnghttp3 \
      libpng libpsl libquadmath libselinux \
      libssh libstdc++ libtirpc libunistring \
      libxcrypt libxml2 libzip libzstd \
      netcdf netcdf-fortran ngtcp2 ngtcp2-crypto-ossl \
      openjpeg openldap openssl-libs pcre2 \
      systemd-libs xz-libs zlib-ng-compat \
 && dnf clean all

ARG MINIFORGE_VERSION=26.1.1-3
ARG MINIFORGE_SHA256=b25b828b702df4dd2a6d24d4eb56cfa912471dd8e3342cde2c3d86fe3dc2d870
RUN curl -fsSL -o /tmp/miniforge.sh \
      "https://github.com/conda-forge/miniforge/releases/download/${MINIFORGE_VERSION}/Miniforge3-Linux-x86_64.sh" \
 && echo "${MINIFORGE_SHA256}  /tmp/miniforge.sh" | sha256sum -c - \
 && bash /tmp/miniforge.sh -b -p /opt/conda \
 && rm /tmp/miniforge.sh

COPY cfpp_sim.yml /tmp/cfpp_sim.yml
RUN /opt/conda/bin/conda env create -f /tmp/cfpp_sim.yml \
 && /opt/conda/bin/conda clean -afy

ENV PATH=/opt/conda/envs/cfpp_sim/bin:/opt/conda/bin:$PATH
ENV ECCODES_DEFINITION_PATH=/usr/share/eccodes/definitions

ARG UID=1000
RUN useradd --create-home --uid "${UID}" chris

# HYSPLIT is NOAA-registered software and is not in this repository. 
# Build with:
#     --build-context hysplit=/PATH/TO/hysplit.v5.4.2_RHEL9.7_public
# and do not push this image to a public registry as that violates HYSPLITs user
# agreement
COPY --from=hysplit --chown=chris:chris . /home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/
RUN cd /home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/exec \
 && missing="$(ldd hycs_std con2cdf4 era52arl chk_file | grep 'not found' || true)" \
 && if [ -n "$missing" ]; then echo "HYSPLIT libraries missing:"; echo "$missing"; exit 1; fi

USER chris
WORKDIR /home/chris/Documents/cfpp_hysplit/HYSPLIT-Simulations-for-CEGB-Power-Plants
CMD ["/bin/bash"]