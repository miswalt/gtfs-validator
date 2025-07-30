import streamlit as st
import os
import sys
import zipfile
import tempfile
import pandas as pd
import pydeck as pdk

from gtfs_core import GTFSDataV2
from gtfs_validator import validate_gtfs
from query_parser import parse_query

if sys.platform == "darwin":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

st.set_page_config(page_title="Transit GTFS Validator and AI Agent", layout="wide")
st.title("🚍 Transit GTFS Validator and AI Agent")

if st.button("🔄 Upload another GTFS file"):
    st.cache_data.clear()
    st.experimental_rerun()

st.markdown("### Upload a GTFS .zip file")
uploaded_file = st.file_uploader("Drag and drop your GTFS ZIP file here", type=["zip"])
st.markdown("### Uploaded Agency")

if uploaded_file is not None:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "gtfs.zip")
        with open(zip_path, "wb") as f:
            f.write(uploaded_file.getvalue())
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmpdir)

        gtfs = GTFSDataV2(tmpdir)

        agency_df = pd.read_csv(os.path.join(tmpdir, "agency.txt"))
        cal_df = pd.read_csv(os.path.join(tmpdir, "calendar.txt"))
        agency_name = agency_df.iloc[0]["agency_name"]
        start = pd.to_datetime(cal_df['start_date'], format='%Y%m%d').min()
        end = pd.to_datetime(cal_df['end_date'], format='%Y%m%d').max()

        st.success(f"✅ Uploaded GTFS for **{agency_name}**: {start.date()} → {end.date()}")

        # --- Map of All Routes with Stops and Route Selector ---
        st.subheader("🗺️ System Map")

        # Get shapes and stops
        shape_segments = gtfs.get_all_shapes()
        stops_df = gtfs.stops.copy()

        # Load route metrics for selector
        route_metrics_df = gtfs.get_route_metrics_summary()
        route_metrics_df["route_name"] = route_metrics_df["short_name"] + " – " + route_metrics_df["long_name"]

        # Build dropdown
        route_names = route_metrics_df["route_name"].sort_values().tolist()
        selected_route_name = st.selectbox("Highlight a route (optional)", ["(All routes)"] + route_names)

        # Get midpoint
        midpoint = {
            "lat": shape_segments[["lat1", "lat2"]].mean().mean(),
            "lon": shape_segments[["lon1", "lon2"]].mean().mean()
        }

        # Determine selected route_id
        if selected_route_name != "(All routes)":
            selected_row = route_metrics_df[route_metrics_df["route_name"] == selected_route_name].iloc[0]
            selected_route_id = selected_row["route_id"]
            selected_shape_ids = gtfs.trips[gtfs.trips["route_id"] == selected_route_id]["shape_id"].dropna().unique()
            highlight_segments = shape_segments[shape_segments["shape_id"].isin(selected_shape_ids)]
        else:
            selected_route_id = None
            highlight_segments = pd.DataFrame(columns=shape_segments.columns)

        # Base layer: all route lines
        base_layer = pdk.Layer(
            "LineLayer",
            data=shape_segments,
            get_source_position='[lon1, lat1]',
            get_target_position='[lon2, lat2]',
            get_color='[180, 180, 180]',
            get_width=2,
            pickable=False
        )

        # Highlighted route
        highlight_layer = pdk.Layer(
            "LineLayer",
            data=highlight_segments,
            get_source_position='[lon1, lat1]',
            get_target_position='[lon2, lat2]',
            get_color='[255, 100, 0]',
            get_width=4,
            pickable=False
        )

        # Stop dots
        stop_layer = pdk.Layer(
            "ScatterplotLayer",
            data=stops_df,
            get_position='[stop_lon, stop_lat]',
            get_radius=20,
            get_color='[200, 200, 200]',
            pickable=False,
            opacity=0.3
        )

        # Render map
        st.pydeck_chart(pdk.Deck(
            initial_view_state=pdk.ViewState(
                latitude=midpoint["lat"],
                longitude=midpoint["lon"],
                zoom=11,
                pitch=0,
            ),
            layers=[base_layer, highlight_layer, stop_layer]
        ))

        # --- Validation
        st.subheader("🧪 GTFS Validation Results")
        issues = validate_gtfs(tmpdir)
        if not issues:
            st.success("All basic validation checks passed! 🎉")
        else:
            for issue in issues:
                st.error(issue)

        # --- Summary Metrics
        st.subheader("📊 GTFS Dataset Summary")
        st.markdown(f"- **Routes**: {len(gtfs.routes)}")
        st.markdown(f"- **Stops**: {len(gtfs.stops)}")
        st.markdown(f"- **Trips**: {len(gtfs.trips)}")

        st.markdown("**Route Metrics:**")
        route_metrics_df = gtfs.get_route_metrics_summary()
        route_metrics_df["route_name"] = route_metrics_df["short_name"] + " – " + route_metrics_df["long_name"]
        st.dataframe(
            route_metrics_df[[
                "route_id", "route_name", "length_miles",
                "weekday_trips_per_day", "avg_headway_min", "weekday_runtime_min"
            ]],
            use_container_width=True, height=500
        )

        # --- Natural Language Queries
        st.subheader("💬 Ask a question about the transit network")
        user_query = st.text_input("Examples: 'Show me a map of Route 10', 'How many stops on Route 5L?'")

        if user_query:
            intent = parse_query(user_query)
            st.write("🧠 Parsed intent:", intent)

            result = gtfs.answer_query(intent)

            if result.get("type") == "map":
                st.subheader(f"🗺️ Map of Route {intent.get('route')}")
                shape_df = result.get("shape")
                stops_df = result.get("stops")

                if shape_df is not None and stops_df is not None:
                    midpoint = shape_df[['lat', 'lon']].mean()
                    st.pydeck_chart(pdk.Deck(
                        initial_view_state=pdk.ViewState(
                            latitude=midpoint['lat'],
                            longitude=midpoint['lon'],
                            zoom=12,
                            pitch=0,
                        ),
                        layers=[
                            pdk.Layer(
                                "LineLayer",
                                data=shape_df,
                                get_source_position='[lon, lat]',
                                get_target_position='[lon, lat]',
                                get_color='[200, 30, 0]',
                                width_scale=10,
                                width_min_pixels=2,
                                pickable=False,
                                auto_highlight=True,
                            ),
                            pdk.Layer(
                                "ScatterplotLayer",
                                data=stops_df,
                                get_position='[lon, lat]',
                                get_radius=50,
                                get_color='[0, 100, 255]',
                                pickable=True,
                            ),
                        ],
                    ))
                else:
                    st.warning("No map data found for this route.")
            else:
                st.subheader("📣 Answer")
                st.write(result["answer"])
