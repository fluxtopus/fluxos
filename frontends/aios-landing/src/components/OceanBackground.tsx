'use client'

import { useEffect, useRef } from 'react'
import * as THREE from 'three'

const vertexShader = `
  uniform float uTime;
  uniform float uPointSize;
  uniform float uFreq1;
  uniform float uAmp1;
  uniform float uSpeed1;
  uniform float uFreq2;
  uniform float uAmp2;
  uniform float uSpeed2;

  // Ripples
  #define MAX_RIPPLES 10
  uniform vec3 uRipples[MAX_RIPPLES]; // x, y (world pos), z (start time)

  varying vec2 vUv;
  varying float vElevation;

  // 2D Random
  float random(vec2 st) {
    return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
  }

  // 2D Value Noise
  float noise(vec2 st) {
    vec2 i = floor(st);
    vec2 f = fract(st);

    float a = random(i);
    float b = random(i + vec2(1.0, 0.0));
    float c = random(i + vec2(0.0, 1.0));
    float d = random(i + vec2(1.0, 1.0));

    vec2 u = f * f * (3.0 - 2.0 * f);

    return mix(a, b, u.x) +
           (c - a) * u.y * (1.0 - u.x) +
           (d - b) * u.x * u.y;
  }

  // Rotation matrix
  mat2 rotate2d(float angle) {
    return mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
  }

  void main() {
    vUv = uv;

    vec3 pos = position;

    // Base Waves
    // Wave layer 1
    vec2 noiseCoord1 = pos.xy * uFreq1 + uTime * uSpeed1;
    float wave1 = noise(noiseCoord1) * uAmp1;

    // Wave layer 2 (rotated 45 degrees, moving opposite direction)
    vec2 noiseCoord2 = rotate2d(0.785398) * pos.xy * uFreq2 - uTime * uSpeed2;
    float wave2 = noise(noiseCoord2) * uAmp2;
    
    float totalWave = wave1 + wave2;

    // Add Ripples
    for(int i = 0; i < MAX_RIPPLES; i++) {
      vec3 ripple = uRipples[i];
      if(ripple.z > 0.0) { // If active (startTime > 0)
        float age = uTime - ripple.z;
        if(age > 0.0) {
           float dist = distance(pos.xy, ripple.xy);
           // Ripple parameters
           float speed = 5.0;
           float freq = 2.0;
           float decay = 1.0 / (1.0 + dist * 0.5 + age * 0.5);
           float strength = 0.8 * exp(-age * 0.8); // Reduced strength from 2.5 to 0.8
           
           // Ring effect
           float ring = sin(dist * freq - age * speed);
           
           // Only apply if wave has reached this point
           if(dist < age * speed) {
             totalWave += ring * strength * decay;
           }
        }
      }
    }

    pos.z = totalWave;
    vElevation = pos.z;

    vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = uPointSize * (300.0 / -mvPosition.z);
  }
`

const fragmentShader = `
  varying vec2 vUv;
  varying float vElevation;

  void main() {
    // Draw square pixels (no discard based on radius)
    // By default gl_POINTS draws squares. We just don't discard.

    // Colors based on Octopus image (Teal/Cyan/Dark Blue) - Darkened & Desaturated for Noctis Minimus vibe
    // Deep Muted Teal Background (Noctis Minimus bg-ish)
    vec3 colorBase = vec3(0.05, 0.08, 0.10); 
    // Muted Mid Teal
    vec3 colorMid = vec3(0.15, 0.25, 0.28);  
    // Soft Cyan Highlight (Desaturated)
    vec3 colorHigh = vec3(0.2, 0.5, 0.55);   

    float t = (vElevation + 1.5) * 0.4; // Adjust range
    
    vec3 color = mix(colorBase, colorMid, smoothstep(0.0, 0.5, t));
    color = mix(color, colorHigh, smoothstep(0.5, 1.0, t));

    // Consistent alpha for pixels
    float alpha = 0.6;

    gl_FragColor = vec4(color, alpha);
  }
`

export default function OceanBackground() {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const container = containerRef.current
    const width = container.clientWidth
    const height = container.clientHeight

    // Scene
    const scene = new THREE.Scene()
    // Add some fog for depth
    scene.fog = new THREE.FogExp2(0x000000, 0.15)

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000)
    camera.position.set(0, 15, 10)
    camera.lookAt(0, 0, 0)

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 1)
    container.appendChild(renderer.domElement)

    // Geometry - High density for points
    const segments = 256
    const geometry = new THREE.PlaneGeometry(60, 60, segments, segments)

    // Material
    const uniforms = {
      uTime: { value: 0 },
      uPointSize: { value: 0.4 }, // Smaller square size (pixels)
      uFreq1: { value: 0.2 },
      uAmp1: { value: 2.0 },
      uSpeed1: { value: 0.15 },
      uFreq2: { value: 0.15 },
      uAmp2: { value: 1.0 },
      uSpeed2: { value: 0.08 },
      uRipples: { value: Array(10 * 3).fill(0) }, // Flattened array for vec3 uniform
    }

    const material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: false,
      // No wireframe, using Points
    })

    // Points instead of Mesh
    const points = new THREE.Points(geometry, material)
    points.rotation.x = -Math.PI * 0.5 // Flat (top down view)
    points.position.y = -5
    scene.add(points)

    // Raycaster for interaction
    const raycaster = new THREE.Raycaster()
    const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 5) // Plane at y = -5 (inverted normal relative to camera looking down?)
    // Actually, visually the mesh is at y=-5, but rotated. It's effectively a plane at y=-5.
    // We can just intersect the mathematical plane at y=-5 for simplicity.

    // Ripple state
    let rippleIndex = 0
    const ripples = new Float32Array(10 * 3) // 10 ripples * 3 values (x, y, startTime)

    // Click handler
    const handleClick = (e: MouseEvent) => {
       // Normalized device coordinates
       const rect = container.getBoundingClientRect()
       const x = ((e.clientX - rect.left) / width) * 2 - 1
       const y = -((e.clientY - rect.top) / height) * 2 + 1

       raycaster.setFromCamera(new THREE.Vector2(x, y), camera)
       
       // Intersect with a mathematical plane at y = -5
       const target = new THREE.Vector3()
       const planeY = -5
       
       // Calculate intersection with y = -5 manually or using Three.js Plane
       // Ray: origin + direction * t
       // origin.y + direction.y * t = planeY
       // t = (planeY - origin.y) / direction.y
       
       // Note: Camera is at y=15 looking at 0,0,0. Mesh is at y=-5.
       // So we want intersection where y = -5.
       
       if (raycaster.ray.direction.y !== 0) {
         const t = (planeY - raycaster.ray.origin.y) / raycaster.ray.direction.y
         if (t > 0) {
           target.copy(raycaster.ray.origin).add(raycaster.ray.direction.multiplyScalar(t))
           
           // Add ripple at target.x, target.z
           const idx = rippleIndex * 3
           ripples[idx] = target.x
           ripples[idx + 1] = target.z // Using z as y in 2D shader logic
           ripples[idx + 2] = clock.getElapsedTime()
           
           // Update uniform
           // Three.js ShaderMaterial uniforms for arrays of vectors can be tricky.
           // Usually passing flat array or array of Vector3.
           // Let's use an array of Vector3 objects for safety with Three.js
           
           if (!uniforms.uRipples.value[rippleIndex]) {
             uniforms.uRipples.value = Array(10).fill(null).map(() => new THREE.Vector3(0,0,-1))
           }
           
           uniforms.uRipples.value[rippleIndex].set(target.x, target.z, clock.getElapsedTime())
           
           rippleIndex = (rippleIndex + 1) % 10
         }
       }
    }
    window.addEventListener('click', handleClick)

    // Animation
    let animationId: number
    const clock = new THREE.Clock()

    // Subtle camera movement
    let mouseX = 0
    let mouseY = 0
    const handleMouseMove = (e: MouseEvent) => {
      mouseX = (e.clientX / width - 0.5) * 0.5
      mouseY = (e.clientY / height - 0.5) * 0.3
    }
    window.addEventListener('mousemove', handleMouseMove)

    const animate = () => {
      animationId = requestAnimationFrame(animate)
      const elapsed = clock.getElapsedTime()

      uniforms.uTime.value = elapsed

      // Subtle camera movement following mouse
      camera.position.x += (mouseX * 2 - camera.position.x) * 0.02
      camera.position.z = 8 + mouseY * 2
      camera.lookAt(0, 0, 0)

      renderer.render(scene, camera)
    }

    animate()

    // Resize
    const handleResize = () => {
      const w = container.clientWidth
      const h = container.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', handleResize)

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('click', handleClick)
      window.removeEventListener('mousemove', handleMouseMove)
      cancelAnimationFrame(animationId)
      renderer.dispose()
      geometry.dispose()
      material.dispose()
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement)
      }
    }
  }, [])

  return (
    <div ref={containerRef} className="fixed inset-0 pointer-events-auto z-0" />
  )
}
