package config

// DeepMerge merges source into destination. 
// If a key exists in both and both are maps, it merges them recursively.
// If a key exists in both and the source is not a map, the source value overwrites the destination.
func DeepMerge(dst, src map[string]interface{}) map[string]interface{} {
	for k, v := range src {
		if v == nil {
			continue
		}

		// If value is a map, check if destination also has a map
		srcMap, isSrcMap := v.(map[string]interface{})
		dstVal, isDstExist := dst[k]
		dstMap, isDstMap := dstVal.(map[string]interface{})

		if isSrcMap && isDstExist && isDstMap {
			// Recursive merge
			dst[k] = DeepMerge(dstMap, srcMap)
		} else {
			// Hard overwrite or new key
			dst[k] = v
		}
	}
	return dst
}
