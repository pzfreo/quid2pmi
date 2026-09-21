# NIST STP2X3D: converts STEP to X3D/X3DOM, including GD&T geometry (--gdt).
#
# It is the renderer behind NIST's STEP File Analyzer, and the only PMI viewer
# here that is not Windows-only, so it gives an independent check on whether the
# annotations quid2pmi writes are well formed.
#
# Debian trixie carries OCCT 7.8.1, which already uses the TKDESTEP/TKDE library
# names STP2X3D links against, so the distro packages are enough and OCCT does
# not have to be built from source.
FROM debian:trixie-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
        libocct-foundation-dev \
        libocct-modeling-algorithms-dev \
        libocct-modeling-data-dev \
        libocct-data-exchange-dev \
        libocct-ocaf-dev \
        libocct-visualization-dev \
    && rm -rf /var/lib/apt/lists/*

ARG STP2X3D_REF=master
RUN git clone --depth 1 --branch "${STP2X3D_REF}" \
        https://github.com/usnistgov/stp2x3d /src

# STP2X3D targets OCCT 8.0, where XCAFDoc_ShapeTool::GetShape returns a
# reference. In 7.8 it returns by value, which cannot bind to TopoDS_Shape&.
# Taking a copy is correct under both.
RUN sed -i 's/TopoDS_Shape& shape = m_shapeTool->GetShape(/TopoDS_Shape shape = m_shapeTool->GetShape(/' \
        /src/STP2X3D/STEP_Reader.cpp

# std::ofstream::open(const wchar_t*) is an MSVC extension; libstdc++ has no
# wide-character overload. Narrowing the path is fine for ASCII paths.
RUN sed -i 's|m_out.open(filePath.c_str(), std::ios::out);|m_out.open(std::string(filePath.begin(), filePath.end()).c_str(), std::ios::out);|' \
        /src/STP2X3D/X3D_Text.h

WORKDIR /src/build
RUN CSF_OCCTIncludePath=/usr/include/opencascade \
    CSF_OCCTLibPath=/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH) \
    cmake -DCMAKE_BUILD_TYPE=Release .. \
 && cmake --build . -j"$(nproc)"

FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        libocct-foundation-7.8 \
        libocct-modeling-algorithms-7.8 \
        libocct-modeling-data-7.8 \
        libocct-data-exchange-7.8 \
        libocct-ocaf-7.8 \
        libocct-visualization-7.8 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/STP2X3D/STP2X3D /usr/local/bin/STP2X3D
WORKDIR /work
ENTRYPOINT ["STP2X3D"]
