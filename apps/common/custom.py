# @Time    : 2019/1/13 11:28
# @Author  : xufqing
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework import serializers
from rest_framework_jwt.authentication import JSONWebTokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_xops.basic import XopsResponse
from rest_framework.generics import ListAPIView
from errno import errorcode
from rest_framework import permissions
import celery

class CommonPagination(PageNumberPagination):
    '''
    分页设置
    '''
    page_size = 10
    page_size_query_param = 'size'


class RbacPermission(BasePermission):
    '''
    自定义权限
    '''
    @classmethod
    def get_permission_from_role(self, request):
        try:
            perms = request.user.roles.values(
                'permissions__method',
            ).distinct()
            return [p['permissions__method'] for p in perms]
        except AttributeError:
            return None

    def has_permission(self, request, view):
        perms = self.get_permission_from_role(request)
        if perms:
            if 'admin' in perms:
                return True
            elif not hasattr(view, 'perms_map'):
                return True
            else:
                perms_map = view.perms_map
                _method = request._request.method.lower()
                for i in perms_map:
                    for method, alias in i.items():
                        if (_method == method or method == '*') and alias in perms:
                            return True

class ObjPermission(BasePermission):
    '''
    对象级权限控制
    '''
    def has_object_permission(self, request, view, obj):
        perms = RbacPermission.get_permission_from_role(request)
        uid = obj.user_id.split(',')
        if 'admin' in perms:
            return True
        elif str(request.user.id) in uid:
            return True

class TreeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField(max_length=20, source='name')
    pid = serializers.PrimaryKeyRelatedField(read_only=True)


class TreeAPIView(ListAPIView):
    '''
    自定义树结构View
    '''
    serializer_class = TreeSerializer
    authentication_classes = (JSONWebTokenAuthentication,)
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(queryset, many=True)
        tree_dict = {}
        tree_data = []
        try:
            for item in serializer.data:
                tree_dict[item['id']] = item
            for i in tree_dict:
                if tree_dict[i]['pid']:
                    pid = tree_dict[i]['pid']
                    parent = tree_dict[pid]
                    parent.setdefault('children', []).append(tree_dict[i])
                else:
                    tree_data.append(tree_dict[i])
            results = tree_data
        except KeyError:
            results = serializer.data
        if page is not None:
            return self.get_paginated_response(results)
        return XopsResponse(results)


class CeleryTools(object):
    '''
    Celery的一些工具
    '''

    def get_celery_worker_status(self):
        d = None
        try:
            insp = celery.task.control.inspect()
            if not insp.stats():
                d = '没有找到可用的celery workers.'
        except IOError as e:
            msg = "无法连接celery backend: " + str(e)
            if len(e.args) > 0 and errorcode.get(e.args[0]) == 'ECONNREFUSED':
                msg += '请检查RabbitMQ是否运行.'
            d = msg
        except ImportError as e:
            d = str(e)
        return d