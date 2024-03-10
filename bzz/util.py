def find_index(predicate, l):
  for i,e in enumerate(l):
    if predicate(e): return i
  return None
  