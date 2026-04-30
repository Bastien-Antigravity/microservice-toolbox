use serde_yml::Value;

/// Recursive deep merge of src into dst.
/// 
/// Behavior matches Go implementation:
/// - If both are mappings, recurse.
/// - Otherwise, overwrite dst with src.
pub fn deep_merge(dst: &mut Value, src: &Value) {
    if let (Some(dst_map), Some(src_map)) = (dst.as_mapping_mut(), src.as_mapping()) {
        for (k, v) in src_map {
            if !dst_map.contains_key(k) || !v.is_mapping() {
                dst_map.insert(k.clone(), v.clone());
            } else {
                deep_merge(dst_map.get_mut(k).unwrap(), v);
            }
        }
    } else {
        *dst = src.clone();
    }
}
