"""
py回炉计划,用来学习class类的,使用类的一些高级特性实现一个ORM
"""


class Field(object):
    __slots__ = ('max_length',)

    def __init__(self, max_length):
        self.max_length = max_length

    def __str__(self):
        return '<%s>' % self.__class__.__name__

    __repr__ = __str__  # 通过 print(Field()) 直接显示


class StringField(Field):
    def __init__(self, max_length=32):
        super(StringField, self).__init__(max_length)


class IntegerField(Field):
    def __init__(self, max_length=32):
        super(IntegerField, self).__init__(max_length)


class ModelMetaclass(type):
    """ metaclass的类名总是以Metaclass结尾,必须从 type 类型派生 """
    def __new__(cls, name, bases, attrs):
        """
        __new__ 的调用在 __init__ 之前, 至少需要传递一个参数cls, cls表示需要实例化的类
        __new__ 必须要有返回值，返回实例化出来的实例
        :param name: 类的名字
        :param bases: 类集成的父类集合
        :param attrs: 类的方法集合
        :return:
        """
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        mappings = dict()
        for k, v in attrs.items():
            # name <StringField:username>
            if isinstance(v, Field):  # 继承至Field,使用isinstance也是返回True
                # print('Found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
        for k in mappings.keys():
            attrs.pop(k)
        attrs['__mappings__'] = mappings  # 保存属性和列的映射关系
        attrs['__table__'] = name.lower()  # 假设表名和类名一致
        """
        关于 type() 和 type.__new__()
        通过type()函数创建的类和直接写class是完全一样的。
        type.__new__() 则是直接创建出一个类的实例
        """
        return type.__new__(cls, name, bases, attrs)  # type()动态创建class


class Model(dict, metaclass=ModelMetaclass):
    """
    metaclass指示Py解释器在创建Model时,要通过ModelMetaclass.__new__()来创建
    """
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):  # 动态返回属性
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def save(self):
        fields = []
        params = []
        args = []
        for k, v in self.__mappings__.items():
            # fields.append(v.name)
            fields.append(k)
            params.append('?')
            args.append(getattr(self, k, None))
        sql = """insert into %s (%s) values (%s)""" % (self.__table__, ','.join(fields), ','.join(params))
        print('SQL: %s' % sql)
        print('ARGS: %s' % str(args))

    def query(self, sql):
        # 假设结果为
        print(sql)
        return QueryDict([dict(id=1, name='wang1', email='xxx1@qq.com', password='123456'),
                          dict(id=2, name='wang2', email='xxx2@qq.com', password='123456')])


class QueryDict:
    def __init__(self, result):
        self.index = 0
        if isinstance(result, dict):
            self.result = [result]
        if isinstance(result, list):
            self.result = result

    def __getitem__(self, n):  # 把对象和实例当作list
        if isinstance(n, int):  # n是索引
            return self.result[n]
        if isinstance(n, slice):  # n是切片
            return self.result[n.start: n.stop]

    def __iter__(self):  # 让对象和实例可以被迭代
        return self  # 实例本身就是迭代对象，故返回自己

    def __next__(self):  # 这地方有点bug啊,不能显示第一个
        self.index += 1
        if self.index >= len(self.result):
            raise StopIteration()
        return self.result[self.index]


class User(Model):
    # 定义类的属性到列的映射：
    id = IntegerField()
    name = StringField(max_length=16)
    email = StringField()
    password = StringField()


if __name__ == '__main__':
    db = User()
    # db.id = 1
    # db.name = 'wang'
    # db.email = 'xxx@qq.com'
    # db.password = '123'
    # db.save()
    r = db.query('select * from user')
    print(r[0])
    print(r[1])
    for i in r:
        print(i)


