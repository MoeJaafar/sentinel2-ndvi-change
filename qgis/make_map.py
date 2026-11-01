"""Build a QGIS project from the pipeline outputs and export a styled map.

Run with the Python that ships with QGIS so PyQGIS is importable, e.g. on
Windows from the OSGeo4W shell or with the python-qgis launcher:

    python-qgis-ltr.bat qgis/make_map.py

Produces:
    qgis/ndvi_change.qgz      project you can open in QGIS
    outputs/qgis_map.png      exported layout (change map, AOI, legend, scale bar)
"""

from __future__ import annotations

import sys
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsColorRampShader,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsLayerTreeLayer,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsRasterShader,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleSymbolRenderer,
    QgsUnitTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QRectF
from qgis.PyQt.QtGui import QColor, QFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
QGIS_DIR = ROOT / "qgis"


def pseudocolor(layer: QgsRasterLayer, stops: list[tuple[float, str, str]]) -> None:
    """Apply a continuous colour ramp to a single-band float raster."""
    ramp = QgsColorRampShader()
    ramp.setColorRampType(QgsColorRampShader.Interpolated)
    ramp.setColorRampItemList(
        [QgsColorRampShader.ColorRampItem(v, QColor(c), label) for v, c, label in stops]
    )
    ramp.setClassificationMode(QgsColorRampShader.Continuous)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    renderer.setClassificationMin(stops[0][0])
    renderer.setClassificationMax(stops[-1][0])
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def add_raster(project: QgsProject, path: Path, name: str, stops, visible: bool) -> QgsRasterLayer:
    layer = QgsRasterLayer(str(path), name)
    if not layer.isValid():
        raise SystemExit(f"could not load {path}")
    pseudocolor(layer, stops)
    project.addMapLayer(layer, False)
    node = project.layerTreeRoot().addLayer(layer)
    node.setItemVisibilityChecked(visible)
    return layer


def main() -> None:
    QgsApplication.setPrefixPath(QgsApplication.prefixPath(), True)
    app = QgsApplication([], False)
    app.initQgis()

    project = QgsProject.instance()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:32637"))
    project.setTitle("Sentinel-2 NDVI change, farmland south-west of Aleppo")

    ndvi_stops = [
        (0.0, "#f7fcb9", "0.0 bare"),
        (0.3, "#addd8e", "0.3"),
        (0.6, "#41ab5d", "0.6"),
        (0.8, "#004529", "0.8 dense"),
    ]
    change_stops = [
        (-0.5, "#a50026", "-0.5 loss"),
        (-0.15, "#fdae61", "-0.15"),
        (0.0, "#ffffbf", "0 stable"),
        (0.15, "#a6d96a", "+0.15"),
        (0.5, "#006837", "+0.5 gain"),
    ]

    # Layer tree order: top of the list draws on top.
    aoi = QgsVectorLayer(str(ROOT / "aoi" / "aleppo_fields.geojson"), "Area of interest", "ogr")
    if not aoi.isValid():
        raise SystemExit("could not load AOI")
    aoi.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {"color": "0,0,0,0", "outline_color": "#000000", "outline_width": "0.6"}
            )
        )
    )
    project.addMapLayer(aoi, False)
    project.layerTreeRoot().addLayer(aoi)

    change = add_raster(project, OUT / "ndvi_change.tif", "NDVI change, Apr 2026 minus Apr 2025", change_stops, True)
    add_raster(project, OUT / "ndvi_after.tif", "NDVI 2026-04-29", ndvi_stops, False)
    add_raster(project, OUT / "ndvi_before.tif", "NDVI 2025-04-21", ndvi_stops, False)

    # Print layout: map, title, legend, scale bar.
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("NDVI change map")
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(272, 200, QgsUnitTypes.LayoutMillimeters))

    title = QgsLayoutItemLabel(layout)
    title.setText("Vegetation change on farmland south-west of Aleppo, Syria")
    title.setFont(QFont("Arial", 16, QFont.Bold))
    title.adjustSizeToText()
    title.attemptMove(QgsLayoutPoint(10, 8, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(title)

    subtitle = QgsLayoutItemLabel(layout)
    subtitle.setText(
        "NDVI difference, Sentinel-2 L2A, 29 April 2026 minus 21 April 2025. "
        "10 m pixels, EPSG:32637. Contains modified Copernicus Sentinel data."
    )
    subtitle.setFont(QFont("Arial", 9))
    subtitle.adjustSizeToText()
    subtitle.attemptMove(QgsLayoutPoint(10, 17, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(subtitle)

    map_item = QgsLayoutItemMap(layout)
    map_item.setRect(QRectF(0, 0, 170, 165))
    map_item.setCrs(project.crs())
    map_item.setLayers([aoi, change])
    extent = change.extent()
    extent.scale(1.03)
    map_item.setExtent(extent)
    map_item.attemptMove(QgsLayoutPoint(10, 25, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(170, 165, QgsUnitTypes.LayoutMillimeters))
    map_item.setFrameEnabled(True)
    layout.addLayoutItem(map_item)

    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Legend")
    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    legend.setWrapString(",")
    legend.setStyleFont(QgsLegendStyle.Title, QFont("Arial", 11, QFont.Bold))
    legend.setStyleFont(QgsLegendStyle.Subgroup, QFont("Arial", 9))
    legend.setStyleFont(QgsLegendStyle.SymbolLabel, QFont("Arial", 8))
    root = legend.model().rootGroup()
    root.clear()
    for lyr in (change, aoi):
        node = root.addLayer(lyr)
        legend.model().refreshLayerLegend(node)
    legend.updateLegend()
    legend.attemptMove(QgsLayoutPoint(188, 25, QgsUnitTypes.LayoutMillimeters))
    legend.setFrameEnabled(True)
    layout.addLayoutItem(legend)

    scalebar = QgsLayoutItemScaleBar(layout)
    scalebar.setLinkedMap(map_item)
    scalebar.setStyle("Single Box")
    scalebar.applyDefaultSize(QgsUnitTypes.DistanceKilometers)
    scalebar.setNumberOfSegments(2)
    scalebar.setNumberOfSegmentsLeft(0)
    scalebar.setUnitsPerSegment(2)
    scalebar.setFont(QFont("Arial", 8))
    scalebar.attemptMove(QgsLayoutPoint(188, 120, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(scalebar)

    credit = QgsLayoutItemLabel(layout)
    credit.setText(
        "Change classes, |dNDVI| > 0.15:\n"
        "  gain 6 259 ha\n"
        "  stable 1 979 ha\n"
        "  loss 88 ha\n\n"
        "Method and code:\n"
        "github.com/MoeJaafar/\n"
        "sentinel2-ndvi-change"
    )
    credit.setFont(QFont("Arial", 8))
    credit.adjustSizeToText()
    credit.attemptMove(QgsLayoutPoint(188, 140, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(credit)

    project.layoutManager().addLayout(layout)

    QGIS_DIR.mkdir(exist_ok=True)
    project_path = QGIS_DIR / "ndvi_change.qgz"
    if not project.write(str(project_path)):
        raise SystemExit("could not write project")

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 200
    result = exporter.exportToImage(str(OUT / "qgis_map.png"), settings)
    if result != QgsLayoutExporter.Success:
        raise SystemExit(f"export failed: {result}")

    print(f"wrote {project_path} and {OUT / 'qgis_map.png'}")
    app.exitQgis()


if __name__ == "__main__":
    sys.exit(main())
