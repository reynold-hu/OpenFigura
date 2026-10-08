extends Node3D
var target: Skeleton3D
var snapshots: Array = []
var rest: Array = []
var modifier: RetargetModifier3D
var ap: AnimationPlayer
var elapsed := 0.0
var requested_frames := 31
func find_type(node: Node, type_name: String) -> Node:
 if node.is_class(type_name): return node
 for child in node.get_children():
  var found = find_type(child,type_name)
  if found: return found
 return null
func meshes(node: Node) -> Array:
 var result: Array = []
 if node is MeshInstance3D: result.append(node)
 for child in node.get_children(): result.append_array(meshes(child))
 return result
func vec(v: Vector3) -> Array: return [v.x,v.y,v.z]
func matrix(t: Transform3D) -> Array: return [vec(t.basis.x),vec(t.basis.y),vec(t.basis.z),vec(t.origin)]
func _ready():
 var cfg = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
 requested_frames = int(cfg["frames"])
 var reference = load("res://reference.glb").instantiate()
 var model = load("res://target.glb").instantiate()
 add_child(reference); add_child(model)
 var source: Skeleton3D = find_type(reference,"Skeleton3D")
 target = find_type(model,"Skeleton3D")
 ap = find_type(reference,"AnimationPlayer")
 assert(source and target and ap)
 for m in meshes(reference): m.visible=false
 var profile := SkeletonProfile.new()
 profile.bone_size=target.get_bone_count()
 var names: Array = []
 for i in target.get_bone_count():
  var name = target.get_bone_name(i)
  assert(source.find_bone(name)>=0,"reference missing bone "+name)
  names.append(name); profile.set_bone_name(i,name)
  rest.append(matrix(target.global_transform*target.get_bone_global_rest(i)))
 for i in target.get_bone_count():
  var parent = target.get_bone_parent(i)
  if parent>=0: profile.set_bone_parent(i,target.get_bone_name(parent))
 var box := AABB()
 var initialized := false
 for m in meshes(model):
  var local_box: AABB = m.get_aabb()
  for i in 8:
   var point: Vector3 = m.global_transform*local_box.get_endpoint(i)
   if initialized: box=box.expand(point)
   else: box=AABB(point,Vector3.ZERO); initialized=true
 modifier=RetargetModifier3D.new(); source.add_child(modifier)
 modifier.profile=profile; modifier.use_global_pose=false
 modifier.set_position_enabled(false);modifier.set_rotation_enabled(true);modifier.set_scale_enabled(false)
 target.reparent(modifier,true)
 modifier.modification_processed.connect(record_frame)
 var env := WorldEnvironment.new();env.environment=Environment.new()
 env.environment.background_mode=Environment.BG_COLOR;env.environment.background_color=Color(.4,.4,.4)
 env.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
 env.environment.ambient_light_color=Color.WHITE;env.environment.ambient_light_energy=.6;add_child(env)
 var key := DirectionalLight3D.new();key.light_energy=1.2;key.rotation_degrees=Vector3(-35,-30,0);add_child(key)
 var camera := Camera3D.new();camera.projection=Camera3D.PROJECTION_ORTHOGONAL;camera.size=box.size.y*1.25
 add_child(camera);camera.position=box.get_center()+Vector3(0,0,box.size.y*4);camera.look_at(box.get_center());camera.current=true
 var clips=ap.get_animation_list();print("RETARGET_SOURCE_CLIPS ",clips)
 var selected_clip = ""
 for clip in clips:
  if clip!="RESET": selected_clip=clip;break
 if selected_clip == "":
  push_error("reference contains no playable non-RESET clip");get_tree().quit(1);return
 ap.play(selected_clip)
 FileAccess.open("res://rest.json",FileAccess.WRITE).store_string(JSON.stringify({"names":names,"rest":rest,"framework":"Godot RetargetModifier3D","mode":"rotation only; use_global_pose=false"}))
func record_frame():
 var poses: Array = []
 for i in target.get_bone_count(): poses.append(matrix(target.global_transform*target.get_bone_global_pose(i)))
 snapshots.append({"frame":snapshots.size()+1,"time":elapsed,"poses":poses})
func _process(delta):
 elapsed+=delta
 if snapshots.size()>=requested_frames:
  FileAccess.open("res://poses.json",FileAccess.WRITE).store_string(JSON.stringify(snapshots))
  print("RETARGET_RECORDED_FRAMES ",snapshots.size())
  get_tree().quit()
