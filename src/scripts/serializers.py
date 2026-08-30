# La vue d'import lit son fichier directement depuis `request.FILES` : il n'y
# a plus de sérialiseur ici. `FileUploadSerializer` a été retiré, il n'était
# référencé nulle part et n'héritait pas de `serializers.Serializer`.
