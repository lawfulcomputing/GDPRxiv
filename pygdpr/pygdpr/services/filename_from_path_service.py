def filename_from_path_service(path):
    subpaths = path.split('/')[-1]
    filename = subpaths.split('.')[0]
    return filename
