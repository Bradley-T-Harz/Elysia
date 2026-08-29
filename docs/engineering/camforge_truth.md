# CAMForge and G-code truth

CAMForge treats G-code as dangerous machine-instruction text and only performs inert, bounded analysis. It reports hash/size, line/comment counts, dialect hints, G/M/T/S/F summaries, G20/G21 units, G90/G91 coordinate modes, extrusion mode, coordinate extents, feed-rate range, spindle/heater/tool/homing/probe/pause commands, mode transitions, work offsets, arcs, and unknown commands.

Risk flags include missing units or coordinate mode, negative Z, rapid moves before homing, spindle start, high heater temperatures, tool changes, probes, unknown M-codes, large feed rates, suspicious arcs, and absolute/relative mode changes. Every result carries a machine-profile compatibility warning; static parsing cannot establish that a program is safe for a specific machine, stock, tool, fixture, material, or operator.

An exact-approved SVG path preview is local and non-executing. It is not a controller simulation. CAMForge has no route or code path to open serial/USB, connect to OctoPrint/Moonraker/CNC/printer/robot controllers, send commands, upload a job, start a spindle/heater/job, or execute an M-code. Physical output is unavailable by design.
