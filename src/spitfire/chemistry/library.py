"""
This module defines containers for tabulated chemistry libraries and solution trajectories
"""

# Spitfire - a Python-C++ library for building tabulated chemistry models and solving differential equations
# Copyright 2019 National Technology & Engineering Solutions of Sandia, LLC (NTESS).
#
# You should have received a copy of the 3-clause BSD License
# along with this program.  If not, see <https://opensource.org/licenses/BSD-3-Clause>.
#
# Questions? Contact Mike Hansen (mahanse@sandia.gov)


import numpy as np
import pickle as pickle
from copy import copy, deepcopy
import shutil
import os


class Dimension(object):
    """A class to contain details of a particular independent variable in a structured library

    **Constructor**: specify a name and list of values

    Parameters
    ----------
    name : str
        the name of the mechanism - hyphens and spaces may not be used here, use underscore separators
    values: np.array
        the values of the independent variable in the grid
    """

    def __init__(self, name: str, values: np.array, log_scaled=False):
        self._name = name
        self._values = np.copy(values)
        self._min = np.min(values)
        self._max = np.max(values)
        self._npts = values.size
        self._log_scaled = log_scaled

        if not name.isidentifier():
            raise ValueError(f'Error in building Dimension "{name}", the name cannot contain hyphens or spaces '
                             f'(it must be a valid Python variable name, '
                             f'note that you can check this with name.isidentifier())')

        if len(self._values.shape) != 1:
            raise ValueError(f'Error in building Dimension "{name}", the values object must be one-dimensional.'
                             f' Use the ravel() method to flatten your data.')

        if self._values.size != np.unique(self._values).size:
            raise ValueError(f'Error in building structured dimension "{name}"'
                             ', duplicate values were identified!')

    def __str__(self):
        return f'Dimension "{self._name}" spanning [{self._min}, {self._max}] with {self._npts} points'

    def __repr__(self):
        return f'Spitfire Dimension(name="{self._name}", min={self._min}, max={self._max}, npts={self._npts})'

    @property
    def name(self):
        """Obtain the name of the independent variable"""
        return self._name

    @property
    def values(self):
        """Obtain the one-dimensional np.array of the specified values of this independent variable"""
        return self._values

    @property
    def min(self):
        return self._min

    @property
    def max(self):
        return self._max

    @property
    def npts(self):
        return self._npts
       
    @property
    def log_scaled(self):
        return self._log_scaled

    def _get_dict_for_file_save(self):
        return {'name': self._name, 'values': self._values, 'log_scaled': self._log_scaled}


class LibraryIndexError(IndexError):
    pass


class Library(object):
    """A container class for tabulated datasets over structured grids.

    Upon constructing the Library object, the following properties are made available on the instance for each Dimension
      library.[dimension_name]_name
      library.[dimension_name]_values
      library.[dimension_name]_min
      library.[dimension_name]_max
      library.[dimension_name]_npts
      library.[dimension_name]_grid = multidimensional meshgrid of the data

    **Constructor**: specify the argument list of dimensions defining the grid

    Parameters
    ----------
    dimensions : argument list of Dimension instances and/or (name, values) tuples
        the dimensions that define the grid

    """

    def _set_grid(self):
        grid = np.meshgrid(*[self._dims[d].values for d in self._dims], indexing='ij')
        self._grid_shape = grid[0].shape
        self._grid_size = grid[0].size

        for i, d in enumerate(self._dims):
            setattr(self, self._dims[d].name, d)
            setattr(self, self._dims[d].name + '_grid', np.copy(grid[i]))
            for a in self._dims[d].__dict__:
                setattr(self, self._dims[d].name + a, getattr(self._dims[d], a))

    def __init__(self, *dimensions):
        self._dims = dict(
            {d.name: (Dimension(d.name, d.values, d.log_scaled) if isinstance(d, Dimension) else Dimension(d[0], d[1], False if len(d) == 2 else d[2])) for d in
             dimensions})
        self._props = dict()
        self._dims_ordering = dict()
        for i, d in enumerate(dimensions):
            self._dims_ordering[i] = d.name

        if dimensions:
            self._set_grid()

        self._extra_attributes = dict()

    def scale_dimension(self, dim_name, multiplier):
        try:
            self.remap_dimension(dim_name, lambda x: multiplier * x)
        except KeyError:
            raise KeyError(f'Invalid dimension name \"{dim_name}\" provided to scale_dimension() on library {self}.')

    def remap_dimension(self, dim_name, mapping):
        try:
            self._dims[dim_name] = Dimension(dim_name, mapping(self._dims[dim_name].values))
            self._set_grid()
        except KeyError:
            raise KeyError(f'Invalid dimension name \"{dim_name}\" provided to remap_dimension() on library {self}.')

    @property
    def extra_attributes(self):
        """Get the extra attributes dictionary of this Library,
            which will be saved in the instance and in any pickle or text files.
            Use this to retain any random information that you might like later,
            such as authorship notes, dates, recommendations for use, etc."""
        return self._extra_attributes

    def __getstate__(self):
        return dict(dimensions={d: self._dims[d]._get_dict_for_file_save() for d in self._dims},
                    dim_ordering=self._dims_ordering,
                    properties=self._props,
                    extra_attributes=self._extra_attributes)

    def __setstate__(self, instance_dict):
        ordered_dims = list([None] * len(instance_dict['dimensions'].keys()))
        for index in instance_dict['dim_ordering']:
            name = instance_dict['dim_ordering'][index]
            d = instance_dict['dimensions'][name]
            ordered_dims[index] = Dimension(d['name'], d['values'], log_scaled=(False if 'log_scaled' not in d else d['log_scaled']))
        self.__init__(*ordered_dims)
        for prop in instance_dict['properties']:
            self[prop] = instance_dict['properties'][prop]
        ea = dict() if 'extra_attributes' not in instance_dict else instance_dict['extra_attributes']
        for p in ea:
            self.extra_attributes[p] = ea[p]

    def save_to_file(self, file_name):
        """Save a library to a specified file using pickle"""
        with open(file_name, 'wb') as file_output:
            pickle.dump(self, file_output)

    def save_to_text_directory(self, output_directory, ravel_order='F', format='%.14e'):
        """
        Dump the contents of a library to a set of easy-to-process text files in a directory.
        Note that file names of property bulk data files will have spaces replaced by underscores.
        Note that the preferred method of saving data for later use with Spitfire is the save_to_file method,
        which dumps compressed data with pickle, Python's native serialization tool. The Library.load_from_file method
        can then be used to reload data into Python, which is significantly faster than loading from text files.
        This method of dumping data does not natively support reloading data from the text files,
        and is simply meant to provide data that is easy to load in other codes (e.g., C++, Fortran, or Matlab codes).

        Parameters
        ----------
        output_directory: str
            where to save the files (a new directory will be made, and an existing one will be removed with permission)
        ravel_order: str
            row-major ('C') or column-major ('F') flattening of multidimensional property arrays, default is 'F' for column-major,
            which flattens the first dimension first, second dimension second, and so on
        format: str
            string format for numbers sent to NumPy savetxt function, default is '%.14e'

        """
        out_dir_exists = os.path.isdir(output_directory)
        proceed = input(
            f'Library.save_to_text_directory(): remove existing directory {output_directory}? (y/any=no) ') if out_dir_exists else 'y'

        if proceed != 'y':
            print('Library.save_to_text_directory(): cannot override existing output directory, aborting!')
            return

        if out_dir_exists:
            shutil.rmtree(output_directory)

        os.mkdir(output_directory)

        md_iv_file_name = os.path.join(output_directory, 'metadata_independent_variables.txt')
        md_dv_file_name = os.path.join(output_directory, 'metadata_dependent_variables.txt')
        md_ea_file_name = os.path.join(output_directory, 'metadata_user_defined_attributes.txt')
        bd_prefix = 'bulkdata'

        prop_names_underscored = dict({p: p.replace(' ', '_') for p in self.props})

        with open(md_iv_file_name, 'w') as f:
            for d in self.dims:
                f.write(d.name + '\n')

        with open(md_dv_file_name, 'w') as f:
            for p in self.props:
                f.write(prop_names_underscored[p] + '\n')

        with open(md_ea_file_name, 'w') as f:
            f.write(str(self._extra_attributes))

        for d in self.dims:
            np.savetxt(os.path.join(output_directory, f'{bd_prefix}_ivar_{d.name}.txt'),
                       d.values, fmt=format)

        for p in self.props:
            np.savetxt(os.path.join(output_directory, f'{bd_prefix}_dvar_{prop_names_underscored[p]}.txt'),
                       self[p].ravel(order=ravel_order), fmt=format)

    @classmethod
    def load_from_file(cls, file_name):
        """Load a library from a specified file name with pickle (following save_to_file)"""
        with open(file_name, 'rb') as file_input:
            pickled_data = pickle.load(file_input)

        if isinstance(pickled_data, dict):  # for compatibility with v1.0 outputs that were pickled as dictionaries
            library = Library()
            library.__setstate__(pickled_data)
            return library
        else:
            return pickled_data

    def __copy__(self):
        new_dimensions = []
        for d in self.dims:
            new_d = Dimension(d.name, d.values, d.log_scaled)
            new_dimensions.append(new_d)
        new_library = Library(*new_dimensions)
        for p in self.props:
            new_library[p] = self[p]
        for ea in self.extra_attributes:
            new_library.extra_attributes[ea] = self.extra_attributes[ea]
        return new_library

    def __deepcopy__(self, *args, **kwargs):
        new_dimensions = []
        for d in self.dims:
            new_d = Dimension(d.name, np.copy(d.values), d.log_scaled)
            new_dimensions.append(new_d)
        new_library = Library(*new_dimensions)
        for p in self.props:
            new_library[p] = np.copy(self[p])
        for ea in self.extra_attributes:
            new_library.extra_attributes[ea] = self.extra_attributes[ea]
        return new_library

    @classmethod
    def copy(cls, library):
        """Shallow copy of a library into a new one"""
        return copy(library)

    @classmethod
    def deepcopy(cls, library):
        """Deep copy of a library into a new one"""
        return deepcopy(library)

    @classmethod
    def squeeze(cls, library):
        """Produce a new library from another by removing dimensions with only one value,
            for instance after slicing, lib_new = Library.squeeze(library[:, 0]).
            Note that if all dimensions are removed, for instance in Library.squeeze(library[0, 1]),
            a dictionary of the scalar values in the following form is returned instead of a new library:
            {'dimensions': {name1: value1, name2: value2, ...}, 'properties': {prop1: value1, ...}, 'extra_attributes': {...}}"""
        new_dimensions = []
        for d in library.dims:
            if d.values.size > 1:
                new_d = Dimension(d.name, d.values, d.log_scaled)
                new_dimensions.append(new_d)
        if not new_dimensions:
            return dict(properties=dict({p: np.squeeze(library[p]) for p in library.props}),
                        dimensions=dict({d.name: (np.squeeze(d.values), d.log_scaled) for d in library.dims}),
                        extra_attributes=library.extra_attributes)
        else:
            new_library = Library(*new_dimensions)
            for p in library.props:
                new_library[p] = np.squeeze(library[p])
            for ea in library.extra_attributes:
                new_library.extra_attributes[ea] = library.extra_attributes[ea]
            return new_library

    @classmethod
    def swapaxes(cls, library, idx1, idx2):
        """Swap the dimension of index idx1 with that of idx2"""
        dim_names = library.dim_names
        if len(dim_names)<2:
            raise ValueError("Cannot perform swap on library with one dimension.")
        dim_names[idx1], dim_names[idx2] = dim_names[idx2], dim_names[idx1]
        swaplib = Library(*[Dimension(d, library.dims[library.dim_names.index(d)].values) for d in dim_names])
        for p in library.props:
            swaplib[p] = np.swapaxes(library[p], idx1, idx2)
        for e in library.extra_attributes:
            swaplib.extra_attributes[e] = library.extra_attributes[e]
        return swaplib

    def __setitem__(self, quantity, values):
        """Use the bracket operator, as in lib['myprop'] = values, to add a property defined on the grid
           The np.ndarray of values must be shaped correctly"""
        if isinstance(values, np.ndarray):
            if values.shape != self._grid_shape:
                raise ValueError(f'The shape of the "{quantity}" array does not conform to that of the library. '
                                 f'Given shape = {values.shape}, grid shape = {self._grid_shape}')
            if quantity not in self._props:
                self._props[quantity] = values.view()
            else:
                self._props[quantity][:] = values
        elif isinstance(values, float) or isinstance(values, int):
            values = float(values) if isinstance(values, int) else values
            if quantity not in self._props:
                self._props[quantity] = self.get_empty_dataset()
            self._props[quantity].fill(values)
        else:
            raise TypeError(f'In Library[arg] = values, values must be a np.ndarray or float, received {values}')

    def __getitem__(self, *slices):
        """Either return the data for a property, as in lib['myprop'], when a single string is provided,
            or obtain an entirely new library that is sliced according to the arguments, as in lib[:, 1:-1, 0, :].
            Only standard slice operations are allowed.
            Note that this will preserve the full dimensionality of a library, even if a dimension has a single value.
            Use the Library.squeeze(lib) class method to remove single-value dimensions if desired.
            Furthermore, this will return a view to the original data. To copy a library, use the copy() and deepcopy()
            methods from the Python copy package or on the Library class (l2 = Library.copy(l1), same for deepcopy)."""

        arg1 = slices[0]
        if isinstance(arg1, str):
            if len(slices) == 1:
                return self._props[arg1]
            else:
                raise LibraryIndexError(f'Library[...] can either take a single string or standard Python slices, '
                                        f'you provided it {slices}')
        else:
            if isinstance(slices[0], slice):
                slices = slices
                if slices[0] == slice(None, None, None) and len(self.dims) > 1:
                    slices = tuple([slice(None, None, None)] * len(self.dims))
            else:
                slices = slices[0]

            if len(slices) != len(self.dims):
                raise LibraryIndexError(
                    f'Library[...] slicing must be given the same number of arguments as there are dimensions, '
                    f'you provided {len(slices)} slices to a Library of dimension {len(self.dims)}')
            new_dimensions = []
            for d, s in zip(self.dims, slices):
                if not isinstance(s, slice) and not isinstance(s, int):
                    raise LibraryIndexError(f'Library[...] can either take a single string or standard Python slices, '
                                            f'you provided it {slices}')
                new_d = Dimension(d.name, np.array([d.values[s]]) if isinstance(d.values[s], float) else d.values[s], d.log_scaled)
                new_dimensions.append(new_d)
            new_library = Library(*new_dimensions)
            for p in self.props:
                new_library[p] = self._props[p][slices].reshape(new_library.shape)
            for ea in self.extra_attributes:
                new_library.extra_attributes[ea] = self.extra_attributes[ea]
            return new_library

    def __contains__(self, prop):
        return prop in self._props

    def __str__(self):
        return f'\nSpitfire Library with {len(self.dims)} dimensions ' + \
               f'and {len(list(self._props.keys()))} properties\n' + \
               f'------------------------------------------\n' + \
               f'\n'.join([f'{i + 1}. {str(d)}' for (i, d) in enumerate(self.dims)]) + \
               f'\n------------------------------------------\n' + \
               f'\n'.join([f'{k:20}, min = {np.min(self._props[k])} max = {np.max(self._props[k])}' for k in
                           self._props.keys()]) + \
               f'\nExtra attributes: {self.extra_attributes}' + \
               f'\n------------------------------------------\n'

    def __repr__(self):
        return f'\nSpitfire Library(ndim={len(self.dims)}, nproperties={len(list(self._props.keys()))})\n' + \
               '\n'.join([f'{i + 1}. {str(d)}' for (i, d) in enumerate(self.dims)]) + \
               f'\nProperties: [{", ".join(list(self._props.keys()))}]' + \
               f'\nExtra attributes: {self.extra_attributes}'

    @property
    def size(self):
        return self._grid_size

    @property
    def shape(self):
        return self._grid_shape

    @property
    def props(self):
        """Obtain a list of the names of properties set on the library"""
        return list(self._props.keys())

    @property
    def dims(self):
        """Obtain the ordered list of the Dimension objects associated with the library"""
        dims = []
        for d in self._dims_ordering:
            dims.append(self._dims[self._dims_ordering[d]])
        return dims

    @property
    def dim_names(self):
        """Obtain the ordered list of the Dimension object names"""
        return [d.name for d in self.dims]

    def dim(self, name):
        """Obtain a Dimension object by name"""
        return self._dims[name]

    def get_empty_dataset(self):
        """Obtain an empty dataset in the shape of the grid, to enable filling one point, line, plane, etc. at a time,
        before then possibly setting a library property with the data"""
        return np.ndarray(self._grid_shape)

    def add_empty_property(self, name):
        self._props[name] = self.get_empty_dataset()

    def remove(self, *quantities):
        """Remove quantities (argument list of strings) from the library"""
        for quantity in quantities:
            self._props.pop(quantity)
