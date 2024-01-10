''' Dereference objects and types from a model.
'''

import copy
import logging
from typing import Callable, List, Optional, Union
from sqlalchemy.orm.session import Session, object_session
from .util import normalize_ident
from .ari import ARI, LiteralARI, ReferenceARI, Identity, StructType
from .typing import BUILTINS_BY_ENUM, BaseType, SemType, TypeUse, type_walk
from .models import AdmModule, AdmObjMixin, Typedef, Ident, Const

LOGGER = logging.getLogger(__name__)

_OBJ_TYPES = {
    StructType.TYPEDEF: Typedef,
    StructType.IDENT: Ident,
    StructType.CONST: Const,
}
''' Map from reference type-ID to ADM model type. '''


class RelativeResolver:
    ''' Resolve module-relative ARIs '''

    def __init__(self, ns_id:Union[int, str]):
        self._ns_id = ns_id

    def __call__(self, ari:ARI) -> ARI:
        if isinstance(ari, ReferenceARI):
            if ari.ident.ns_id is None:
                ari.ident = Identity(
                    ns_id=self._ns_id,
                    type_id=ari.ident.type_id,
                    obj_id=ari.ident.obj_id,
                )
        return ari


def dereference(ref:ReferenceARI, db_sess:Session) -> Optional[AdmObjMixin]:
    ''' Dereference a single object reference.
    '''
    orm_type = _OBJ_TYPES[ref.ident.type_id]

    ns_id = ref.ident.ns_id
    query_adm = db_sess.query(AdmModule)
    if isinstance(ns_id, int):
        query_adm = query_adm.filter(AdmModule.enum == ns_id)
    elif isinstance(ns_id, str):
        query_adm = query_adm.filter(AdmModule.norm_name == normalize_ident(ns_id))
    else:
        raise TypeError('ReferenceARI ns_id is not int or str')
    found_adm = query_adm.one_or_none()
    if found_adm is None:
        return None

    obj_id = ref.ident.obj_id
    query_obj = (
        db_sess.query(orm_type)
        .filter(orm_type.module == found_adm)
    )
    if isinstance(obj_id, int):
        query_obj = query_obj.filter(orm_type.enum == obj_id)
    elif isinstance(obj_id, str):
        query_obj = query_obj.filter(orm_type.norm_name == normalize_ident(obj_id))
    else:
        raise TypeError('ReferenceARI obj_id is not int or str')
    found_obj = query_obj.one_or_none()
    return found_obj


class TypeResolverError(RuntimeError):

    def __init__(self, msg:str, badtypes:List):
        super().__init__(msg)
        self.badtypes = badtypes


class TypeResolver:
    ''' A caching recursive type resolver.
    '''

    def __init__(self):
        self._cache = dict()
        self._badtypes = None
        self._db_sess = None

    def resolve(self, typeobj:SemType, adm:'AdmModule') -> SemType:
        ''' Bind references to external BaseType objects from type names.
        This function is not reentrant.

        :param typeobj: The original unbound type object (and any children).
        :return: The :ivar:`typeobj` with all type references bound.
        :raise TypeResolverError: If any required types are missing.
        '''
        if typeobj is None:
            return None

        self._badtypes = set()
        self._db_sess = object_session(adm)
        LOGGER.debug('Resolver started')
        for sub_obj in type_walk(typeobj):
            self._typeuse_bind(sub_obj)
        LOGGER.debug('Resolver finished with %d bad', len(self._badtypes))
        if self._badtypes:
            raise TypeResolverError(f'Missing types to bind to: {self._badtypes}', self._badtypes)

        for sub_obj in type_walk(typeobj):
            self._constraint_bind(sub_obj)

        # Verify type use constraint applicability
        # for sub_obj in type_walk(typeobj):
        #     if isinstance(sub_obj, TypeUse):
        #         have_types = sub_obj.type_ids()
        #         for constr in sub_obj.constraints:
        #             need_one_type = constr.applicable()
        #             LOGGER.warning('type constraint needs %s', need_one_type)
        #             met_types = need_one_type & have_types
        #             if not met_types:
        #                 raise TypeResolverError(f'Constraint needs {need_one_type} but have only {have_types}', [])

        self._badtypes = None
        self._db_sess = None
        return typeobj

    def _typeuse_bind(self, obj:'BaseType'):
        ''' A type visitor suitable for binding :cls:`TypeUse` objects
        from type references.
        '''
        if not isinstance(obj, TypeUse):
            return

        if obj.base is not None:
            # already bound, nothing to do
            return

        basetypeobj = None
        typedef = None
        LOGGER.debug('type search for %s', obj.type_ari)
        if isinstance(obj.type_ari, LiteralARI):
            basetypeobj = BUILTINS_BY_ENUM[obj.type_ari.value]
        elif isinstance(obj.type_ari, ReferenceARI):
            try:
                typedef = dereference(obj.type_ari, self._db_sess)
                if not isinstance(typedef, Typedef):
                    typedef = None
            except TypeError:
                typedef = None

            if typedef is None:
                self._badtypes.add(obj.type_ari.ident)
        else:
            self._badtypes.add(obj.type_ari)

        if basetypeobj:
            obj.base = basetypeobj
        elif typedef:
            key = (typedef.module.norm_name, typedef.norm_name)
            cached = self._cache.get(key)
            if cached:
                obj.base = cached
            else:
                # recursive binding
                typeobj = copy.copy(typedef.typeobj)
                # cache object before recursion
                self._cache[key] = typeobj

                LOGGER.debug('recurse binding %s for %s', typedef.norm_name, typeobj)
                for sub_obj in type_walk(typeobj):
                    self._typeuse_bind(sub_obj)

                obj.base = typeobj

        LOGGER.debug('result for %s bound %s', obj.type_ari, obj.base)

    def _constraint_bind(self, obj:'BaseType') -> None:
        ''' Bindi :cls:`Constraint` objects to local DB session.
        '''
        from .type_constraint import IdentRefBase

        if not isinstance(obj, TypeUse):
            return

        for cnst in obj.constraints:
            if isinstance(cnst, IdentRefBase):
                try:
                    ident = dereference(cnst.base_ari, self._db_sess)
                    if not isinstance(ident, Ident):
                        ident = None
                except TypeError:
                    ident = None
            if ident is None:
                self._badtypes.add(cnst.base_ari.ident)
            else:
                cnst.base_ident = ident
