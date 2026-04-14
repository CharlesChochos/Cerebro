"use client";

import { useEffect, useRef, type RefObject } from "react";
import type { Viewer } from "cesium";

// ─── Module-level singleton ───
// Survives HMR and prevents multiple WebGL contexts fighting over the same canvas.
// React strict mode + HMR can trigger multiple effect runs that each try to create
// a viewer. Without this guard, we get "object does not belong to this context" WebGL
// errors and corrupted framebuffers.
let activeViewer: Viewer | null = null;
let initPromise: Promise<void> | null = null;

function destroyActiveViewer() {
  if (activeViewer && !activeViewer.isDestroyed()) {
    activeViewer.destroy();
  }
  activeViewer = null;
  initPromise = null;
}

/**
 * Custom hook that imperatively creates and manages a CesiumJS Viewer.
 *
 * Imagery strategy:
 * - With Ion token: default Bing Maps (best quality)
 * - Without Ion token: NaturalEarthII (bundled) + ESRI World Imagery overlay
 *
 * CRITICAL notes:
 * - Do NOT pass `baseLayer: false` — it kills the rAF render loop.
 * - Module-level singleton prevents WebGL context conflicts from strict mode + HMR.
 */
export function useCesiumViewer(
  containerRef: RefObject<HTMLDivElement | null>,
  options?: {
    ionToken?: string;
    onReady?: (viewer: Viewer) => void;
  }
): RefObject<Viewer | null> {
  const viewerRef = useRef<Viewer | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // If a viewer already exists (from HMR or strict mode), reuse it
    // if it's still attached to our container, or destroy it if it's orphaned.
    if (activeViewer && !activeViewer.isDestroyed()) {
      if (activeViewer.container === containerRef.current) {
        // Same container — reuse existing viewer (HMR case)
        viewerRef.current = activeViewer;
        options?.onReady?.(activeViewer);
        return;
      }
      // Different container — destroy the old one
      destroyActiveViewer();
    }

    // Prevent concurrent initialization (strict mode fires effect twice rapidly)
    if (initPromise) return;

    if (typeof window !== "undefined") {
      (window as unknown as Record<string, unknown>).CESIUM_BASE_URL = "/cesium/";
    }

    let destroyed = false;

    initPromise = import("cesium").then(async (Cesium) => {
      await import("cesium/Build/Cesium/Widgets/widgets.css");

      if (destroyed || !containerRef.current) {
        initPromise = null;
        return;
      }

      const token = options?.ionToken || process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN || "";
      const hasIonToken = token.length > 10;

      if (hasIonToken) {
        Cesium.Ion.defaultAccessToken = token;
      }

      // ─── Destroy any leftover viewer (belt-and-suspenders) ───
      destroyActiveViewer();

      if (destroyed || !containerRef.current) {
        initPromise = null;
        return;
      }

      // ─── Create viewer ───
      // Without Ion token, Bing Maps tiles will 401 silently.
      // The render loop still runs fine — we replace imagery below.
      const viewer = new Cesium.Viewer(containerRef.current!, {
        animation: false,
        timeline: false,
        fullscreenButton: false,
        homeButton: false,
        sceneModePicker: false,
        baseLayerPicker: false,
        navigationHelpButton: false,
        geocoder: false,
        infoBox: false,
        selectionIndicator: false,
        creditContainer: document.createElement("div"),
        msaaSamples: 2,
      });

      if (destroyed) {
        viewer.destroy();
        initPromise = null;
        return;
      }

      // Track the singleton
      activeViewer = viewer;

      const scene = viewer.scene;
      const globe = scene.globe;

      // ─── Globe configuration ───
      globe.show = true;
      globe.enableLighting = false;
      globe.depthTestAgainstTerrain = false;
      globe.baseColor = Cesium.Color.fromCssColorString("#1e3a5f");

      if (scene.skyAtmosphere) scene.skyAtmosphere.show = true;
      if (scene.fog) scene.fog.enabled = true;
      if (scene.sun) scene.sun.show = true;
      if (scene.moon) scene.moon.show = true;
      if (scene.skyBox) (scene.skyBox as unknown as { show: boolean }).show = true;
      scene.backgroundColor = Cesium.Color.fromCssColorString("#0a0a0a");

      // ─── Replace default imagery when no Ion token ───
      if (!hasIonToken) {
        // Remove the default Bing Maps layer (which 401s without Ion token)
        if (viewer.imageryLayers.length > 0) {
          viewer.imageryLayers.removeAll();
        }

        // Add NaturalEarthII (bundled local tiles — instant, guaranteed)
        try {
          const tmsProvider = await Cesium.TileMapServiceImageryProvider.fromUrl(
            "/cesium/Assets/Textures/NaturalEarthII"
          );
          if (!viewer.isDestroyed()) {
            viewer.imageryLayers.addImageryProvider(tmsProvider);
          }
        } catch (e) {
          console.warn("Cesium: NaturalEarthII failed:", e);
        }

        // Add ESRI World Imagery (high-res satellite, zoom 0-23)
        try {
          const esriProvider = await Cesium.ArcGisMapServerImageryProvider.fromUrl(
            "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer"
          );
          if (!viewer.isDestroyed()) {
            viewer.imageryLayers.addImageryProvider(esriProvider);
          }
        } catch (e) {
          console.warn("Cesium: ESRI overlay failed:", e);
        }

        if (!viewer.isDestroyed()) {
          scene.requestRender();
        }
      }

      // ─── Terrain (Ion-only) ───
      if (hasIonToken) {
        try {
          const terrain = await Cesium.createWorldTerrainAsync({
            requestVertexNormals: true,
            requestWaterMask: true,
          });
          if (!viewer.isDestroyed()) {
            viewer.terrainProvider = terrain;
            globe.depthTestAgainstTerrain = true;
          }
        } catch (e) {
          console.warn("Cesium: Could not load world terrain:", e);
        }
      }

      // ─── 3D Buildings (Ion-only) ───
      if (hasIonToken) {
        try {
          const buildings = await Cesium.createOsmBuildingsAsync();
          if (!viewer.isDestroyed()) scene.primitives.add(buildings);
        } catch (e) {
          console.warn("Cesium: Could not load OSM buildings:", e);
        }
      }

      if (viewer.isDestroyed()) return;

      // ─── Camera defaults ───
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(20, 30, 15_000_000),
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(-90),
          roll: 0,
        },
        duration: 0,
      });

      viewer.screenSpaceEventHandler.removeInputAction(
        Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK
      );

      // ─── Fallback render pump ───
      // Browsers throttle rAF to 0fps in hidden tabs. This ensures tiles
      // still load. Self-clears once initial tiles are loaded.
      const pumpId = setInterval(() => {
        if (viewer.isDestroyed()) {
          clearInterval(pumpId);
          return;
        }
        if (document.hidden || scene.frameState.frameNumber < 30) {
          scene.render();
        }
        if (globe.tilesLoaded) {
          clearInterval(pumpId);
        }
      }, 100);

      viewerRef.current = viewer;
      initPromise = null;
      options?.onReady?.(viewer);
    });

    // Cleanup — handles React strict mode double-mount
    return () => {
      destroyed = true;
      // Don't destroy the viewer here in dev mode — the strict mode remount
      // will try to reuse it. Only nullify the ref.
      viewerRef.current = null;
      initPromise = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Destroy viewer on true unmount (component removed from tree)
  useEffect(() => {
    return () => {
      destroyActiveViewer();
      viewerRef.current = null;
    };
  }, []);

  return viewerRef;
}
