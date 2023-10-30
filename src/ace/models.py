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
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.orderinglist import ordering_list
import ace.ari

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


class TypeNameList(Base):
    ''' A list of typed, named items (e.g. parameters or columns) '''
    __tablename__ = "typename_list"
    ''' Logical list of type/name items for an ADM object.
    Used by CTRL and EDD for parameters and TBLT for columns.

    There is no explicit relationship to the object which contains this type.
    '''
    id = Column(Integer, primary_key=True)

    items = relationship("TypeNameItem", order_by="TypeNameItem.position",
                         collection_class=ordering_list('position'), cascade="all, delete")


class TypeNameItem(Base):
    ''' Each item within a TypeNameList '''
    __tablename__ = "typename_item"
    id = Column(Integer, primary_key=True)

    # Containing list
    list_id = Column(Integer, ForeignKey("typename_list.id"))
    list = relationship("TypeNameList", back_populates="items")
    # ordinal of this parameter in a TypeNameList
    position = Column(Integer)

    type = Column(String)
    name = Column(String, nullable=False)


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
    # Detail description
    description = Column(String)
    # Current revision
    revision = Column(String)

    uses = relationship("AdmUses", back_populates="admfile",
                        order_by='asc(AdmUses.position)',
                        cascade="all, delete")

    semtype = relationship("SemType", back_populates="admfile",
                           cascade="all, delete")

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


class AdmUses(Base):
    ''' Each "uses" of an ADM '''
    __tablename__ = "adm_uses"
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="uses")
    # ordinal of this item in the list
    position = Column(Integer)

    # Original exact text
    namespace = Column(String)

    # Normalized text for searching    
    norm_namespace = Column(String, index=True)


class SemType(Base):
    ''' Semantic type definition, may be used with a typedef or an anonymous type. '''
    __tablename__ = "semtype"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="semtype")

    # Relationship to the :class:`Typedef`
    typedef = relationship("Typedef")

    # Only one of the following will be present
    base_type = Column(String)

    # Columns present in the table
    columns_id = Column(Integer, ForeignKey('typename_list.id'), nullable=False)
    columns = relationship("TypeNameList", cascade="all, delete")


class AdmObjMixin:
    ''' Common attributes of an ADM-defined object. '''
    # Unique name (within a section)
    name = Column(String, nullable=False)
    # Arbitrary optional text
    description = Column(String)

    # Normalized object name (for searching)
    norm_name = Column(String, index=True)
    # Enumeration for this ADM
    enum = Column(Integer, index=True)

# These following classes are all proper ADM top-level object sections.


class Typedef(Base, AdmObjMixin):
    ''' Type definition (named semantic type) '''
    __tablename__ = "typedef"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="typedef")

    # ID of the named type
    semtype_id = Column(Integer, ForeignKey("semtype.id"))
    # Relationship to the :class:`SemType`
    semtype = relationship("SemType", back_populates="typedef")


class Edd(Base, AdmObjMixin):
    ''' Externally Defined Data (EDD) '''
    __tablename__ = "edd"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="edd")

    # Named or anonymous type
    semtype_id = Column(Integer, ForeignKey("semtype.id"))
    semtype = relationship("SemType")
    # Parameters of this object
    parmspec_id = Column(Integer, ForeignKey("typename_list.id"))
    parmspec = relationship("TypeNameList", cascade="all, delete")


class Const(Base, AdmObjMixin):
    ''' Constant value (CONST) '''
    __tablename__ = "const"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="const")

    # Named or anonymous type
    semtype_id = Column(Integer, ForeignKey("semtype.id"))
    semtype = relationship("SemType")

    value = Column(String)


class Ctrl(Base, AdmObjMixin):
    ''' Control '''
    __tablename__ = "ctrl"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="ctrl")

    # Parameters of this object
    parmspec_id = Column(Integer, ForeignKey("typename_list.id"))
    parmspec = relationship("TypeNameList", cascade="all, delete")


class Oper(Base, AdmObjMixin):
    ''' Operator (Oper) used in EXPR postfix '''
    __tablename__ = "oper"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="oper")

    result_type = Column(String)
    in_type = relationship("OperParm", order_by="OperParm.position",
                           collection_class=ordering_list('position'),
                           cascade="all, delete")


class OperParm(Base):
    ''' Defining each parameter used by an Oper '''
    __tablename__ = "oper_parm"
    id = Column(Integer, primary_key=True)
    # ID of the Oper for which this is a parameter
    oper_id = Column(Integer, ForeignKey("oper.id"))
    # Relationship to the parent :class:`Oper`
    oper = relationship("Oper", back_populates="in_type")
    # ordinal of this parameter in an Oper
    position = Column(Integer)

    type = Column(String)


class Var(Base, AdmObjMixin):
    ''' Variable value (VAR)'''
    __tablename__ = "var"
    # Unique ID of the row
    id = Column(Integer, primary_key=True)
    # ID of the file from which this came
    admfile_id = Column(Integer, ForeignKey("admfile.id"))
    # Relationship to the :class:`AdmFile`
    admfile = relationship("AdmFile", back_populates="var")

    # Named or anonymous type
    semtype_id = Column(Integer, ForeignKey("semtype.id"))
    semtype = relationship("SemType")

    initializer_id = Column(Integer, ForeignKey('expr.id'))
    initializer = relationship("Expr")
