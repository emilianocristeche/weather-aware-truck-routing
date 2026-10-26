import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .service import PlanError, plan_trip


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


# Stateless JSON API with no cookies or sessions, so CSRF does not apply.
@csrf_exempt
@require_POST
def plan(request):
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Request body must be JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Request body must be a JSON object."}, status=400)
    try:
        return JsonResponse(plan_trip(payload))
    except PlanError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
