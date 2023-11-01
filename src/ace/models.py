#
# Copyright (c) 2023 The Johns Hopkins University Applied Physics
# Laboratory LLC.
#
# This file is part of the Asynchronous Network Managment System (ANMS).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This work was performed for the Jet Propulsion Laboratory, California
# Institute of Technology, sponsored by the United States Government under
# the prime contract 80NM0018D0004 between the Caltech and NASA under
# subcontract 1658085.
#
''' ORM models for the ADM and its contents.
'''
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import (
    declarative_base, relationship, declared_attr, Mapped
)
from sqlalchemy.ext.orderinglist import ordering_list

# Value of :attr:`SchemaVersion.version_num`
CURRENT_SCHEMA_VERSION = 12

Base = declarative_base()

# pylint: disable=too-few-public-methods


class SchemaVersion(Base):
    ''' Identify the version of a DB. '''
    __tablename__ = "schema_version"
    version_num = Column(Integer, primary_key=True)

# These first classes are containers and are not explicitly bound to a
# parent ADM object.


class CommonMixin:
    ''' Common module substatements. '''
    description = Column(String)


class MetadataItem(Base):
    ''' A single item of module, object, or substatement metadata. '''
    __tablename__ = "metadata_item"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey("metadata_list.id"))
    list = relationship("MetadataList", back_populates="items")

    name = Column(String, nullable=False)
    arg = Column(String, nullable=False)


class MetadataList(Base):
    ''' A list of named metadata items.

    There is no explicit relationship to the object which contains this type.
    '''
    __tablename__ = "metadata_list"
    id = Column(Integer, primary_key=True)

    items = relationship(
        "MetadataItem",
        order_by="MetadataItem.name",
        collection_class=ordering_list('name'),
        cascade="all, delete"
    )


class TypeUse(Base):
    ''' Attributes for typed (value producing) objects and 
    typed sub-statements.
    
    Built-in types will not have an associated :ivar:`semtype`, 
    just an unrefined :ivar:`type_name` reference.
    '''
    __tablename__ = "type_use"
    id = Column(Integer, primary_key=True)

    # Optional relationship to a parent :class:`Typedef`
    typedef = relationship("Typedef", viewonly=True)

    # ADM module name for a non-builtin :ivar:`type_name`
    type_ns = Column(String)
    # Name of builtin or namespaced typedef
    type_name = Column(String)
    # Refinements for used type
    type_refinements = relationship(
        "TypeRefinement",
        order_by="TypeRefinement.position",
        collection_class=ordering_list('position'),
        cascade="all, delete"
    )

    # Columns present in the table template
    columns_id = Column(Integer, ForeignKey('typename_list.id'))
    columns = relationship("TypeNameList", cascade="all, delete")


class TypeRefinement(Base):
    ''' Each item within a TypeNameList '''
    __tablename__ = "type_refinement"
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey("type_use.id"))
    list = relationship("TypeUse", back_populates="type_refinements")
    # ordinal of this item in a :cls:`TypeUse`
    position = Column(Integer)

    name = Column(String, nullable=False)
    value = Column(String)


class TypeUseMixin:
    ''' Common attributes for referencing a :cls:`TypeUse` instance. '''
    typeuse_id = Column(Integer, ForeignKey("type_use.id"))

    @declared_attr
    def typeuse(self) -> Mapped["TypeUse"]:
        return relationship("TypeUse", foreign_keys=[self.typeuse_id], cascade="all, delete")


class TypeNameList(Base):
    ''' A list of typed, named items (e.g. parameters or columns).

    There is no explicit relationship to the object which contains this type.
    '''
    __tablename__ = "typename_list"
    id = Column(Integer, primary_key=True)

    items = relationship(
        "TypeNameItem",
        order_by="TypeNameItem.position",
        collection_class=ordering_list('position'),
        cascade="all, delete"
    )


class TypeNameItem(Base, TypeUseMixin):
    ''' Each item within a TypeNameList '''
    __tablename__ = "typename_item"
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey("typename_list.id"))
    list = relationship("TypeNameList", back_populates="items")
    # ordinal of this item in a TypeNameList
    position = Column(Integer)

    # Unique name for the item, the type comes from :cls:`TypeUseMixin`
    name = Column(String, nullable=False)
    # Arbitrary optional text
    description = Column(String)


class ARI(Base):
    ''' A single non-literal ARI '''
    __tablename__ = "ari"
    id = Column(Integer, primary_key=True)

    # Optional containing AC
    list_id = Column(Integer, ForeignKey("ac.id"))
    # Relationship to the :class:`AC`
    list = relationship("AC", back_populates="items")
    # ordinal of this parameter in an AC (if part of an AC)
    position = Column(Integer)

    # Namespace
    ns = Column(String)
    # Name
    nm = Column(String)
    # Optional parameters
    ap = relationship("AriAP", order_by="AriAP.position",
                      collection_class=ordering_list('position'),
                      cascade="all, delete")


class AriAP(Base):
    ''' Defining each parameter used by an ARI '''
    __tablename__ = "ari_ap"
    id = Column(Integer, primary_key=True)
    # ID of the Oper for which this is a parameter
    ari_id = Column(Integer, ForeignKey("ari.id"))
    # Relationship to the parent :class:`Oper`
    ari = relationship("ARI", back_populates="ap")
    # ordinal of this parameter in an ARI list
    position = Column(Integer)

    type = Column(String)
    value = Column(String)


class AC(Base):
    ''' An ARI Collection (AC).
    Used by macros to define the action, used by reports to define the contents.

    There is no explicit relationship to the object which contains this type.
    '''
    __tablename__ = "ac"
    id = Column(Integer, primary_key=True)

    items = relationship("ARI", order_by="ARI.position",
                         collection_class=ordering_list('position'),
                         cascade="all, delete")


class Expr(Base):
    ''' Expression (EXPR) '''
    __tablename__ = "expr"
    id = Column(Integer, primary_key=True)

    # Result type of the expression
    type = Column(String)
    # The AC defining the postfix expression
    postfix_id = Column(Integer, ForeignKey('ac.id'))
    # Relationship to the :class:`AC`
    postfix = relationship("AC")


class AdmFile(Base):
    ''' The ADM file itself and its source (filesystem) metadata '''
    __tablename__ = "admfile"

    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # Fully resolved path from which the ADM was loaded
    abs_file_path = Column(String)
    # Modified Time from the source file
    last_modified = Column(DateTime)

    # Normalized ADM name (for searching)
    name = Column(String)
    # Normalized ADM name (for searching)
    norm_name = Column(String, index=True)
    # Enumeration for this ADM
    enum = Column(Integer, index=True)

    metadata_id = Column(Integer, ForeignKey('metadata_list.id'), nullable=False)
    metadata_list = relationship(
        "MetadataList",
        cascade="all, delete"
    )

    revisions = relationship(
        "AdmRevision",
        back_populates="admfile",
        order_by='asc(AdmRevision.position)',
        cascade="all, delete"
    )

    imports = relationship(
        "AdmImport",
        back_populates="admfile",
        order_by='asc(AdmImport.position)',
        cascade="all, delete"
    )

    # references a list of contained objects
    typedef = relationship("Typedef", back_populates="admfile",
                           order_by='asc(Typedef.enum)',
                           cascade="all, delete")
    const = relationship("Const", back_populates="admfile",
                         order_by='asc(Const.enum)',
                         cascade="all, delete")
    ctrl = relationship("Ctrl", back_populates="admfile",
                        cascade="all, delete")
    edd = relationship("Edd", back_populates="admfile",
                       order_by='asc(Edd.enum)',
                       cascade="all, delete")
    oper = relationship("Oper", back_populates="admfile",
                        order_by='asc(Oper.enum)',
                        cascade="all, delete")
    var = relationship("Var", back_populates="admfile",
                       order_by='asc(Var.enum)',
                       cascade="all, delete")

    def __repr__(self):
        repr_attrs = ('id', 'norm_name', 'abs_file_path', 'last_modified')
        parts = [f"{attr}={getattr(self, attr)}" for attr in repr_attrs]
        return "ADM(" + ', '.join(parts) + ")"


class AdmRevision(Base, CommonMixin):
    ''' Each "revision" of an ADM '''
    __tablename__ = "adm_revision"
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="revisions")
    # ordinal of this item in the list
    position = Column(Integer)

    # Original exact text, indexed for sorting
    name = Column(String, index=True)


class AdmImport(Base, CommonMixin):
    ''' Each "import" of an ADM '''
    __tablename__ = "adm_import"
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="imports")
    # ordinal of this item in the list
    position = Column(Integer)

    # Original exact text
    name = Column(String)
    # Prefix within the module
    prefix = Column(String)


class AdmObjMixin(CommonMixin):
    ''' Common attributes of an ADM-defined object. '''
    # ordinal of this item in the module
    position = Column(Integer)

    # Unique name (within a section)
    name = Column(String, nullable=False)
    # Normalized object name (for searching)
    norm_name = Column(String, index=True)

    # Enumeration for this ADM
    enum = Column(Integer, index=True)


class ParamMixin:
    ''' Attributes for formal parameters of an object. '''
    # Parameters of this object
    parameters_id = Column(Integer, ForeignKey("typename_list.id"))

    # Relationship to the :class:`TypeNameList`
    @declared_attr
    def parameters(self) -> Mapped["TypeNameList"]:
        return relationship(
            "TypeNameList",
            foreign_keys=[self.parameters_id],
            cascade="all, delete"
        )

# These following classes are all proper ADM top-level object sections.


class Typedef(Base, AdmObjMixin, TypeUseMixin):
    ''' Type definition (named semantic type) '''
    __tablename__ = "typedef"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="typedef")


class Edd(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Externally Defined Data (EDD) '''
    __tablename__ = "edd"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="edd")


class Const(Base, AdmObjMixin, ParamMixin, TypeUseMixin):
    ''' Constant value (CONST) '''
    __tablename__ = "const"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="const")

    # The initial and constant value ARI
    value = Column(String)


class Ctrl(Base, AdmObjMixin, ParamMixin):
    ''' Control '''
    __tablename__ = "ctrl"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="ctrl")


class Oper(Base, AdmObjMixin, ParamMixin):
    ''' Operator (Oper) used in EXPR postfix '''
    __tablename__ = "oper"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="oper")

    operands_id = Column(Integer, ForeignKey('typename_list.id'), nullable=False)
    operands = relationship("TypeNameList",
                            foreign_keys=[operands_id],
                            cascade="all, delete")

    result_id = Column(Integer, ForeignKey("typename_item.id"), nullable=False)
    result = relationship("TypeNameItem", foreign_keys=[result_id], cascade="all, delete")


class Var(Base, AdmObjMixin, TypeUseMixin):
    ''' Variable value (VAR)'''
    __tablename__ = "var"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="var")

    # Initial value expression
    initializer_id = Column(Integer, ForeignKey('expr.id'))
    initializer = relationship("Expr")
