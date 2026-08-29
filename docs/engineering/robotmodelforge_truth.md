# RobotModelForge capability truth

RobotModelForge performs defused, bounded XML inspection of URDF and SDF without launching a robotics runtime.

URDF reports link/joint counts and joint types, parent-child graph, roots, cycles and missing-link references, visual/collision geometry, inertial presence, bounded mass/inertia sanity warnings, joint limits, materials, transmissions, Gazebo tags, mesh dependencies, and `package://` references. Xacro syntax is detected and explicitly not expanded. Inertial data is never treated as validated or safe.

SDF reports version plus world/model/link/joint/sensor/plugin counts, physics declarations, includes and URIs, mesh references, collision/visual/inertial counts, nested models, lights, and cameras. Plugins are warnings only; their filenames or bodies are never loaded. `model://`, `fuel://`, HTTP(S), absolute, traversal, and other external references are classified but not fetched.

RobotModelForge does not launch ROS, `robot_state_publisher`, RViz, Gazebo/gz, controllers, or plugins; it does not open robot hardware; and it does not resolve package roots implicitly. Preview and dry-run simulation remain plan-only. Robot control and physical actuation are unavailable by design.
