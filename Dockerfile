# Snapshot of the machine the CEGB power plant HYSPLIT simulations ran on:
# Fedora 44, the cfpp_sim environment, HYSPLIT v5.4.2, and the original
# directory layout, so the code runs unmodified. See README.md, "Option B".

FROM --platform=linux/amd64 fedora:44

RUN dnf -y install --setopt=install_weak_deps=False libgfortran \
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
ENV ECCODES_DEFINITION_PATH=/opt/conda/envs/cfpp_sim/share/eccodes/definitions

ARG UID=1000
RUN useradd --create-home --uid "${UID}" chris

# HYSPLIT is NOAA-registered software and is not in this repository. Build with:
#  --build-context hysplit=/path/to/hysplit.v5.4.2_RHEL9.7_public
# and do not push this image to a public registry.
COPY --from=hysplit --chown=chris:chris . /home/chris/opt/hysplit/hysplit.v5.4.2_RHEL9.7_public/

USER chris
WORKDIR /home/chris/Documents/cfpp_hysplit/HYSPLIT-Simulations-for-CEGB-Power-Plants
CMD ["/bin/bash"]