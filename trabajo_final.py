from pathlib import Path

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium

#Seteamos constantes de url base para cargar los archivos de datos y geoespaciales
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "dataset_tarea_ind.xlsx"
GEOJSON_FILE = BASE_DIR / "comunas_metropolitana.geojson"

#Realizamos la configuración inicial de la página de Streamlit
st.set_page_config(
    page_title="Dashboard geoespacial de ventas",
    page_icon="🗺️",
    layout="wide",
)

#Usamos lo recomendado por el profesor para cargar los datos con caching y evitar recargas
@st.cache_data
def cargar_datos():
    try:
        df = pd.read_excel(DATA_FILE, engine="openpyxl")
    except ImportError:
        st.error("Falta instalar la libreria openpyxl para poder leer el archivo Excel.")
        st.stop()
# Realizamos limpieza y transformación de datos, solicitada para el análisis posterior
    columnas_numericas = ["venta_neta", "lat", "lng", "kms_dist", "lat_cd", "lng_cd"]
    for columna in columnas_numericas:
        df[columna] = (
            df[columna]
            .astype(str)
            .str.replace(",", ".", regex=False)
        )
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    for columna in ["orden", "unidades", "productos"]:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")

    df["fecha_compra"] = pd.to_datetime(df["fecha_compra"], format="%d-%m-%y", errors="coerce")
    df["ordenes"] = 1
    df["mes"] = df["fecha_compra"].dt.to_period("M").dt.to_timestamp()

    for columna in ["canal", "centro_dist", "comuna", "city", "state"]:
        df[columna] = df[columna].astype(str).str.strip()

    df = df.dropna(subset=["fecha_compra", "lat", "lng", "lat_cd", "lng_cd"]).copy()
    return df

#Realizamos nuevamente un caching para cargar el archivo geojson
@st.cache_data
def cargar_comunas():
    comunas = gpd.read_file(GEOJSON_FILE)
    comunas["name"] = comunas["name"].astype(str).str.strip()
    return comunas

#Función para formatear valores monetarios en pesos chilenos
def formatear_pesos(valor):
    return f"${valor:,.0f}".replace(",", ".")

#Función para aplicar los filtros seleccionados por el usuario en la barra lateral
def filtrar_datos(df):
    st.sidebar.header("Filtros")

    fecha_min = df["fecha_compra"].min().date()
    fecha_max = df["fecha_compra"].max().date()
    rango = st.sidebar.date_input(
        "Rango de fechas",
        value=(fecha_min, fecha_max),
        min_value=fecha_min,
        max_value=fecha_max,
    )

    if isinstance(rango, tuple) and len(rango) == 2:
        fecha_inicio, fecha_fin = rango
    else:
        fecha_inicio = fecha_min
        fecha_fin = fecha_max

    canales = st.sidebar.multiselect(
        "Canal",
        options=sorted(df["canal"].unique().tolist()),
        default=sorted(df["canal"].unique().tolist()),
    )
    centros = st.sidebar.multiselect(
        "Centro de distribucion",
        options=sorted(df["centro_dist"].unique().tolist()),
        default=sorted(df["centro_dist"].unique().tolist()),
    )
    comunas = st.sidebar.multiselect(
        "Comuna",
        options=sorted(df["comuna"].unique().tolist()),
        default=sorted(df["comuna"].unique().tolist()),
    )

    distancia_min = float(df["kms_dist"].min())
    distancia_max = float(df["kms_dist"].max())
    rango_distancia = st.sidebar.slider(
        "Rango de distancia (km)",
        min_value=round(distancia_min, 1),
        max_value=round(distancia_max, 1),
        value=(round(distancia_min, 1), round(distancia_max, 1)),
        step=0.5,
    )

    venta_min = int(df["venta_neta"].min())
    venta_max = int(df["venta_neta"].max())
    rango_venta = st.sidebar.slider(
        "Rango de venta neta",
        min_value=venta_min,
        max_value=venta_max,
        value=(venta_min, venta_max),
        step=1000,
    )

    df_filtrado = df[
        (df["fecha_compra"].dt.date >= fecha_inicio)
        & (df["fecha_compra"].dt.date <= fecha_fin)
        & (df["canal"].isin(canales))
        & (df["centro_dist"].isin(centros))
        & (df["comuna"].isin(comunas))
        & (df["kms_dist"] >= rango_distancia[0])
        & (df["kms_dist"] <= rango_distancia[1])
        & (df["venta_neta"] >= rango_venta[0])
        & (df["venta_neta"] <= rango_venta[1])
    ].copy()

    return df_filtrado

#Función para mostrar los KPIs principales en la parte superior del dashboard
def mostrar_kpis(df):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ventas netas", formatear_pesos(df["venta_neta"].sum()))
    col2.metric("Pedidos", f"{int(df['ordenes'].sum()):,}".replace(",", "."))
    col3.metric("Ticket promedio", formatear_pesos(df["venta_neta"].mean()))
    col4.metric("Distancia promedio", f"{df['kms_dist'].mean():.1f} km")

#Funciones para crear los gráficos estadísticos y mapas que se mostrarán en las diferentes pestañas del dashboard
def grafico_barras_canal(df):
    ventas_canal = df.groupby("canal", as_index=False)["venta_neta"].sum()
    ventas_canal = ventas_canal.sort_values("venta_neta", ascending=False).set_index("canal")
    st.bar_chart(ventas_canal, height=320)

#Función para crear gráfico de barras con los 8 centros de distribución con mayores ventas netas
def grafico_barras_centros(df):
    ventas_centros = df.groupby("centro_dist", as_index=False)["venta_neta"].sum()
    ventas_centros = ventas_centros.sort_values("venta_neta", ascending=False).head(8)
    spec = {
        "mark": {"type": "bar", "cornerRadiusEnd": 6},
        "encoding": {
            "y": {
                "field": "centro_dist",
                "type": "nominal",
                "sort": "-x",
                "title": "Centro de distribucion",
                "axis": {"labelLimit": 280},
            },
            "x": {
                "field": "venta_neta",
                "type": "quantitative",
                "title": "Ventas netas",
            },
            "tooltip": [
                {"field": "centro_dist", "type": "nominal", "title": "Centro"},
                {"field": "venta_neta", "type": "quantitative", "title": "Ventas netas"},
            ],
            "color": {"value": "#4f8bf9"},
        },
        "height": 360,
    }
    st.vega_lite_chart(ventas_centros, spec, use_container_width=True)

#Función para crear gráfico de líneas mostrando la evolución diaria de ventas netas y pedidos
def grafico_linea_tiempo(df):
    serie = df.groupby("fecha_compra", as_index=False)[["venta_neta", "ordenes"]].sum()
    st.line_chart(serie.set_index("fecha_compra"), height=360)

#Función para crear un mapa con los centros de distribución y una muestra de puntos de entrega, mostrando información relevante en los popups
def crear_mapa_logistico(df):
    mapa = folium.Map(
        location=[df["lat"].mean(), df["lng"].mean()],
        zoom_start=10,
        tiles="CartoDB positron",
    )

    centros = (
        df.groupby("centro_dist", as_index=False)
        .agg(
            lat_cd=("lat_cd", "first"),
            lng_cd=("lng_cd", "first"),
            ventas=("venta_neta", "sum"),
            pedidos=("ordenes", "sum"),
        )
    )

    for _, fila in centros.iterrows():
        folium.Marker(
            location=[fila["lat_cd"], fila["lng_cd"]],
            tooltip=fila["centro_dist"],
            popup=(
                f"<b>{fila['centro_dist']}</b><br>"
                f"Ventas: {formatear_pesos(fila['ventas'])}<br>"
                f"Pedidos: {int(fila['pedidos'])}"
            ),
            icon=folium.Icon(color="red", icon="home"),
        ).add_to(mapa)

    muestra = df[["lat", "lng", "comuna", "canal", "venta_neta"]].dropna()
    if len(muestra) > 1500:
        muestra = muestra.sample(1500, random_state=42)

    for _, fila in muestra.iterrows():
        folium.CircleMarker(
            location=[fila["lat"], fila["lng"]],
            radius=3,
            color="#1d3557",
            fill=True,
            fill_color="#457b9d",
            fill_opacity=0.35,
            popup=(
                f"<b>{fila['comuna']}</b><br>"
                f"Canal: {fila['canal']}<br>"
                f"Venta: {formatear_pesos(fila['venta_neta'])}"
            ),
        ).add_to(mapa)

    return mapa

#Función para crear un mapa de calor mostrando la concentración de ventas, pedidos, unidades o productos según la selección del usuario
def crear_heatmap(df, metrica):
    mapa = folium.Map(
        location=[df["lat"].mean(), df["lng"].mean()],
        zoom_start=10,
        tiles="CartoDB dark_matter",
    )

    datos = df[["lat", "lng", metrica]].dropna().copy()
    if datos.empty:
        return mapa

    maximo = datos[metrica].max()
    minimo = datos[metrica].min()

    if maximo == minimo:
        datos["peso"] = 1
    else:
        datos["peso"] = (datos[metrica] - minimo) / (maximo - minimo) + 0.1

    HeatMap(
        data=datos[["lat", "lng", "peso"]].values.tolist(),
        radius=18,
        blur=12,
        min_opacity=0.35,
    ).add_to(mapa)

    return mapa

#Función para crear un mapa de coropletas por comuna, coloreando según la métrica seleccionada
def crear_coropleta(df, comunas_gdf, metrica):
    resumen = (
        df.groupby("comuna", as_index=False)
        .agg(
            venta_neta=("venta_neta", "sum"),
            ordenes=("ordenes", "sum"),
            unidades=("unidades", "sum"),
            productos=("productos", "sum"),
            ticket_promedio=("venta_neta", "mean"),
        )
    )

    comunas_mapa = comunas_gdf.merge(resumen, left_on="name", right_on="comuna", how="left")

    mapa = folium.Map(location=[-33.45, -70.66], zoom_start=10, tiles="CartoDB positron")

    folium.Choropleth(
        geo_data=comunas_mapa.__geo_interface__,
        data=comunas_mapa,
        columns=["name", metrica],
        key_on="feature.properties.name",
        fill_color="YlOrRd",
        fill_opacity=0.8,
        line_opacity=0.4,
        legend_name=metrica.replace("_", " ").title(),
        nan_fill_color="#d9d9d9",
    ).add_to(mapa)

    tooltip = folium.GeoJsonTooltip(
        fields=["name", "venta_neta", "ordenes", "unidades", "productos", "ticket_promedio"],
        aliases=["Comuna", "Ventas", "Pedidos", "Unidades", "Productos", "Ticket promedio"],
        localize=True,
        sticky=False,
    )

    folium.GeoJson(
        comunas_mapa.__geo_interface__,
        style_function=lambda x: {
            "fillColor": "#00000000",
            "color": "#495057",
            "weight": 0.8,
        },
        tooltip=tooltip,
    ).add_to(mapa)

    return mapa

#Funciones para crear los gráficos estadísticos y mapas que se mostrarán en las diferentes pestañas del dashboard
def panorama_general(df):
    st.subheader("Panorama general del negocio")
    st.caption("Esta pestaña usa solo gráficos estadísticos tradicionales, sin mapas ni tablas.")
    mostrar_kpis(df)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Ventas netas por canal**")
        grafico_barras_canal(df)

    with col2:
        st.markdown("**Top 8 centros por ventas netas**")
        grafico_barras_centros(df)

    st.markdown("**Evolución diaria de ventas y pedidos**")
    grafico_linea_tiempo(df)

#Función para crear un mapa con los centros de distribución y una muestra de puntos de entrega, mostrando información relevante en los popups
def mapa_logistico(df):
    st.subheader("Mapa de la red logística")
    st.caption("Muestra centros de distribución y una muestra de puntos de entrega.")
    mapa = crear_mapa_logistico(df)
    st_folium(mapa, width="stretch", height=560)

#Función para crear un mapa de calor mostrando la concentración de ventas, pedidos, unidades o productos según la selección del usuario
def mapa_calor(df):
    st.subheader("Mapa de calor")
    opcion = st.radio(
        "Ponderar intensidad por",
        ["venta_neta", "ordenes", "unidades", "productos"],
        horizontal=True,
    )
    mapa = crear_heatmap(df, opcion)
    st_folium(mapa, width="stretch", height=560)

#Función para crear un mapa de coropletas por comuna, coloreando según la métrica seleccionada
def mapa_coropleta(df, comunas_gdf):
    st.subheader("Mapa de coropletas por comuna")
    opcion = st.selectbox(
        "Métrica para colorear las comunas",
        ["venta_neta", "ordenes", "unidades", "productos"],
    )
    mapa = crear_coropleta(df, comunas_gdf, opcion)
    st_folium(mapa, width="stretch", height=560)

    resumen = (
        df.groupby("comuna", as_index=False)
        .agg(
            venta_neta=("venta_neta", "sum"),
            ordenes=("ordenes", "sum"),
            unidades=("unidades", "sum"),
            productos=("productos", "sum"),
        )
        .sort_values(opcion, ascending=False)
        .head(12)
    )
    st.dataframe(resumen, use_container_width=True, hide_index=True)

#Función para mostrar un resumen por centro de distribución, con ventas netas, pedidos y distancia promedio, ordenado por ventas netas
#Se explica en el punto 5 del notebook
def sintesis(df):
    st.subheader("Demanda por distribución")
    st.caption("Resumen por centro de distribución para apoyar la recomendación final.")

    resumen = (
        df.groupby("centro_dist", as_index=False)
        .agg(
            venta_neta=("venta_neta", "sum"),
            ordenes=("ordenes", "sum"),
            kms_dist=("kms_dist", "mean"),
        )
        .sort_values("venta_neta", ascending=False)
    )

    spec = {
        "mark": {"type": "bar", "cornerRadiusEnd": 6},
        "encoding": {
            "y": {
                "field": "centro_dist",
                "type": "nominal",
                "sort": "-x",
                "title": "Centro de distribucion",
                "axis": {"labelLimit": 320},
            },
            "x": {
                "field": "venta_neta",
                "type": "quantitative",
                "title": "Ventas netas",
            },
            "tooltip": [
                {"field": "centro_dist", "type": "nominal", "title": "Centro"},
                {"field": "venta_neta", "type": "quantitative", "title": "Ventas netas"},
                {"field": "ordenes", "type": "quantitative", "title": "Pedidos"},
                {"field": "kms_dist", "type": "quantitative", "title": "Distancia promedio"},
            ],
            "color": {"value": "#1f77b4"},
        },
        "height": 420,
    }
    st.vega_lite_chart(resumen, spec, use_container_width=True)
    st.dataframe(resumen, use_container_width=True, hide_index=True)

#Función principal
def main():
    st.title("Dashboard geoespacial de ventas y logística")
    st.write("Aplicación en Streamlit con gráficos estadísticos y mapas Folium.")

    df = cargar_datos()
    comunas_gdf = cargar_comunas()
    df_filtrado = filtrar_datos(df)

    if df_filtrado.empty:
        st.warning("No hay datos para los filtros seleccionados.")
        return

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "1. Panorama general",
            "2. Red logística",
            "3. Heatmap",
            "4. Coropleta",
            "5. Síntesis",
        ]
    )

    with tab1:
        panorama_general(df_filtrado)
    with tab2:
        mapa_logistico(df_filtrado)
    with tab3:
        mapa_calor(df_filtrado)
    with tab4:
        mapa_coropleta(df_filtrado, comunas_gdf)
    with tab5:
        sintesis(df_filtrado)


if __name__ == "__main__":
    main()
