from fastapi import Request
from fastapi.responses import ORJSONResponse
from routers import Router
from common.prepare import prepare_cache_keys, prepare_request, merge_value_to_key

# search/id call local cache optimization

router = Router()


@router.api_route("/api/v3/audit/audit/", methods=["GET", "POST"])
async def audit_audit(request: Request) -> ORJSONResponse:
    parameters, request_headers, endpoint_url, dispatcher = await prepare_request(
        router.settings, request
    )
    packages_list = parameters.get("package")
    if packages_list and isinstance(packages_list, str):
        packages_list = [packages_list]

    cache_args = parameters.get("os"), parameters.get("version")
    cache_keys = prepare_cache_keys(packages_list, cache_args)

    cached_results = router.cache.get_many(cache_keys)
    packages_data = {
        cache_keys[key]: value
        for key, value in cached_results.items()
        if key in cache_keys
    }
    uncached_packages = list(set(packages_list).difference(packages_data.keys()))

    if uncached_packages:
        parameters["package"] = uncached_packages
        request = router.session.build_request(
            method=request.method, url=endpoint_url, json=parameters, headers=request_headers
        )
        vulners_response = await router.session.send(request)
        vulners_response.read()
        vulners_results = vulners_response.json()
        response_packages = {**vulners_results.get("data").get("packages")}
        response_packages.update({
            key: 'empty'
            for key in uncached_packages
            if key not in response_packages
        })
        prepared_cache = {
            merge_value_to_key(package, cache_args): data
            for package, data in response_packages.items()
        }
        router.cache.set_many(
            prepared_cache, expire=router.settings.cache_timeout
        )
    else:
        router.statistics[dispatcher] += 1
        vulners_results = {
            "result": "OK",
            "data": {"packages": {}},
        }
    vulners_results["data"]["packages"].update({
        key: value
        for key, value in packages_data.items()
        if value != 'empty'
    })
    return ORJSONResponse(
        content=vulners_results,
    )
