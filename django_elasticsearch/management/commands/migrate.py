# python
import logging
import pprint

# django
from django.conf import settings
from django.db import connections, DEFAULT_DB_ALIAS
from django.core.management.base import BaseCommand

# pyes
from pyes.exceptions import IndexAlreadyExistsException

# django_elasticsearch
from django_elasticsearch.mapping import model_to_mapping
from django_elasticsearch.models import get_settings_by_meta
from django_elasticsearch import ENGINE

__author__ = 'jorgealegre'

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        engine = settings.DATABASES.get(DEFAULT_DB_ALIAS, {}).get('ENGINE', '')
        global_index_name = settings.DATABASES.get(DEFAULT_DB_ALIAS, {}).get('NAME', '')
        options = settings.DATABASES.get(DEFAULT_DB_ALIAS, {}).get('OPTIONS', {})
        connection = connections[DEFAULT_DB_ALIAS]
        es_connection = connection.connection

        # Call regular migrate if engine is different from ours
        if engine != ENGINE:
            return super(Command, self).handle(**options)
        else:
            try:
                connection.ops.delete_index(global_index_name)
                connection.ops.delete_index('.django_engine')
            except:
                pass

            connection.ops.build_django_engine_structure()
            try:
                index_name_final, alias = connection.ops.create_index(global_index_name, options)
                self.stdout.write(u'index "{}" created with physical name "{}"'.format(alias, index_name_final))
            except IndexAlreadyExistsException:
                pass
            logger.debug(u'models: {}'.format(connection.introspection.models))
            for app_name, app_models in connection.introspection.models.iteritems():
                for model in app_models:
                    self.stdout.write(u'Creating mappings for {}.{}'.format(app_name, model.__name__))
                    mapping = model_to_mapping(model, es_connection, global_index_name)
                    try:
                        mapping.save()
                        self.stdout.write(u'Mapping updated')
                    except Exception as e:
                        self.stdout.write(u'Could not update mapping, rebuilding global index...')
                        connection.ops.rebuild_index(global_index_name)
                        mapping.save()
                    logger.debug(u'Created mapping: {}'.format(
                        pprint.PrettyPrinter(indent=4).pformat(mapping.as_dict())))
                    if not hasattr(model._meta, 'indices'):
                        continue
                    for model_index in model._meta.indices:
                        model_index_name = model_index.keys()[0]
                        index_name = u'{}__{}'.format(model._meta.db_table, model_index_name)
                        index_data = model_index[index_name]
                        try:
                            index_physical, alias = connection.ops.create_index(index_name,
                                                                                get_settings_by_meta(index_data))
                            self.stdout.write(u'index "{}" created with physical name "{}"'.format(alias,
                                                                                                   index_physical))
                        except IndexAlreadyExistsException:
                            pass
                        # build mapping based on index_data
                        if 'routing_field' in index_data:
                            mapping = model_to_mapping(model, es_connection, index_name, _routing={
                                'required': True,
                                'path': index_data['routing_field']
                            })
                        else:
                            mapping = model_to_mapping(model, es_connection, index_name)
                        self.stdout.write(u'Creating mappings for {}'.format(model))
                        logger.debug(u'creating mapping: {}'.format(
                            pprint.PrettyPrinter(indent=4).pformat(mapping.as_dict())))
                        try:
                            mapping.save()
                            self.stdout.write(u'Mappings updated')
                        except Exception as e:
                            self.stdout.write(u'Could not update mapping, rebuilding index "{}" ...'
                                              .format(index_name))
                            connection.ops.rebuild_index(index_name)
                            mapping.save()
