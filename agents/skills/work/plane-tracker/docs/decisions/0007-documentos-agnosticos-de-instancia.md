---
id: "0007"
title: Los documentos del repositorio son agnósticos de instancia, empresa y personas
status: aceptado
created: 2026-10-31
summary: Ningún documento del repo contiene hosts, IPs, nombres de personas o clientes ni datos de horas reales; la evidencia concreta vive fuera del repo.
---

# 0007 · Los documentos del repositorio son agnósticos de instancia, empresa y personas

## Contexto

El repositorio es público y la herramienta puede usarla cualquier persona con su propio Plane. Documentos anteriores incluían la IP de una instancia, el identificador del workspace, nombres de personas y de clientes, y tablas de horas reales por reunión. Eso ya está publicado en el historial de git.

## Decisión

- Los documentos usan roles ("líder técnico", "área comercial"), claves de ejemplo (`PROJ-123`) y hosts de ejemplo (`https://plane.example.com`).
- Los datos concretos de una instancia (host, workspace, personas, clientes, horas reales) viven en la configuración local o en el propio Plane, nunca en el repo.
- Quitar un dato de los archivos actuales no lo borra del historial; reescribir el historial es una decisión aparte y explícita.

## Consecuencias

- Los documentos nuevos pasan este filtro antes de entrar al repo.
- Los documentos anteriores se sanean de forma incremental; lo pendiente se registra como defecto.
